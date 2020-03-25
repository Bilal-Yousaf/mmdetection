import numpy as np
import torch
import torch.nn as nn

from mmdet.core import bbox2result
from .base import BaseDetector
from .. import builder
from ..registry import DETECTORS


@DETECTORS.register_module
class SingleStageDetector(BaseDetector):
    """Base class for single-stage detectors.

    Single-stage detectors directly and densely predict bounding boxes on the
    output features of the backbone+neck.
    """

    def __init__(self,
                 backbone,
                 neck=None,
                 bbox_head=None,
                 train_cfg=None,
                 test_cfg=None,
                 pretrained=None):
        super(SingleStageDetector, self).__init__()
        self.backbone = builder.build_backbone(backbone)
        if neck is not None:
            self.neck = builder.build_neck(neck)
        self.bbox_head = builder.build_head(bbox_head)
        self.train_cfg = train_cfg
        self.test_cfg = test_cfg
        self.init_weights(pretrained=pretrained)

    def init_weights(self, pretrained=None):
        super(SingleStageDetector, self).init_weights(pretrained)
        self.backbone.init_weights(pretrained=pretrained)
        if self.with_neck:
            if isinstance(self.neck, nn.Sequential):
                for m in self.neck:
                    m.init_weights()
            else:
                self.neck.init_weights()
        self.bbox_head.init_weights()

    def extract_feat(self, img):
        """Directly extract features from the backbone+neck
        """
        x = self.backbone(img)
        if self.with_neck:
            x = self.neck(x)
        return x

    def forward_dummy(self, img):
        """Used for computing network flops.

        See `mmedetection/tools/get_flops.py`
        """
        x = self.extract_feat(img)
        outs = self.bbox_head(x)
        return outs

    def forward_train(self,
                      img,
                      img_metas,
                      gt_bboxes,
                      gt_labels,
                      gt_bboxes_ignore=None):
        x = self.extract_feat(img)
        outs = self.bbox_head(x)
        loss_inputs = outs + (gt_bboxes, gt_labels, img_metas, self.train_cfg)
        losses = self.bbox_head.loss(
            *loss_inputs, gt_bboxes_ignore=gt_bboxes_ignore)
        return losses

    def simple_test(self, img, img_meta, rescale=False, postprocess=True):
        x = self.extract_feat(img)
        outs = self.bbox_head(x)
        det_bboxes, det_labels = \
            self.bbox_head.get_bboxes(*outs, img_meta, self.test_cfg, False)[0]

        if postprocess:
            return self.postprocess(det_bboxes, det_labels, None, None, img_meta,
                                    rescale=rescale)

        return det_bboxes, det_labels

    def postprocess(self,
                    det_bboxes,
                    det_labels,
                    det_keypoints,
                    det_masks,
                    img_meta,
                    rescale=False):
        num_classes = self.bbox_head.num_classes

        if rescale:
            scale_factor = img_meta[0]['scale_factor']
            if isinstance(det_bboxes, torch.Tensor):
                det_bboxes[:, :4] /= det_bboxes.new_tensor(scale_factor)
                if det_keypoints is not None:
                    det_keypoints /= det_keypoints.new_tensor(scale_factor[:2])
            else:
                det_bboxes[:, :4] /= np.asarray(scale_factor)
                if det_keypoints is not None:
                    det_keypoints /= np.asarray(scale_factor[:2])

        bbox_results, keypoints_results = bbox2result(det_bboxes, det_labels, det_keypoints, num_classes)
        return bbox_results, keypoints_results

    def aug_test(self, imgs, img_metas, rescale=False):
        raise NotImplementedError
