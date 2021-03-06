import torch

from mmdet.core.utils.misc import arange, meshgrid


class AnchorGenerator(object):
    """
    Examples:
        >>> from mmdet.core import AnchorGenerator
        >>> self = AnchorGenerator(9, [1.], [1.])
        >>> all_anchors = self.grid_anchors((2, 2), device='cpu')
        >>> print(all_anchors)
        tensor([[ 0.,  0.,  8.,  8.],
                [16.,  0., 24.,  8.],
                [ 0., 16.,  8., 24.],
                [16., 16., 24., 24.]])
    """

    def __init__(self, base_size, scales, ratios, scale_major=True, ctr=None,
                 widths=None, heights=None):
        self.base_size = base_size
        if widths is not None and heights is not None:
            self.clustered = True
            assert len(heights) == len(widths)
            self.heights = torch.Tensor(heights)
            self.widths = torch.Tensor(widths)
        else:
            self.clustered = False
            self.scales = torch.Tensor(scales)
            self.ratios = torch.Tensor(ratios)
            self.scale_major = scale_major

        self.ctr = ctr
        self.base_anchors = self.gen_base_anchors()

    @property
    def num_base_anchors(self):
        return self.base_anchors.size(0)

    def gen_base_anchors(self):
        w = self.base_size
        h = self.base_size
        if self.ctr is None:
            x_ctr = 0.5 * (w - 1)
            y_ctr = 0.5 * (h - 1)
        else:
            x_ctr, y_ctr = self.ctr

        if self.clustered:
            ws = self.widths
            hs = self.heights
        else:
            h_ratios = torch.sqrt(self.ratios)
            w_ratios = 1 / h_ratios
            if self.scale_major:
                ws = (w * w_ratios[:, None] * self.scales[None, :]).view(-1)
                hs = (h * h_ratios[:, None] * self.scales[None, :]).view(-1)
            else:
                ws = (w * self.scales[:, None] * w_ratios[None, :]).view(-1)
                hs = (h * self.scales[:, None] * h_ratios[None, :]).view(-1)

        # yapf: disable
        base_anchors = torch.stack(
            [
                x_ctr - 0.5 * (ws - 1), y_ctr - 0.5 * (hs - 1),
                x_ctr + 0.5 * (ws - 1), y_ctr + 0.5 * (hs - 1)
            ],
            dim=-1).round()
        # yapf: enable

        return base_anchors

    def grid_anchors(self, featmap_size, stride=16, device='cuda'):
        base_anchors = self.base_anchors.to(device)

        shift_x = arange(
            start=0, end=featmap_size[1], dtype=torch.float32,
            device=device) * stride
        shift_y = arange(
            start=0, end=featmap_size[0], dtype=torch.float32,
            device=device) * stride
        shift_xx, shift_yy = meshgrid(shift_x, shift_y)
        shifts = torch.stack([shift_xx, shift_yy, shift_xx, shift_yy], dim=1)
        shifts = shifts.type_as(base_anchors)
        # first feat_w elements correspond to the first row of shifts
        # add A anchors (1, A, 4) to K shifts (K, 1, 4) to get
        # shifted anchors (K, A, 4), reshape to (K*A, 4)

        all_anchors = base_anchors[None, :, :] + shifts[:, None, :]
        all_anchors = all_anchors.view(-1, 4)
        # first A rows correspond to A anchors of (0, 0) in feature map,
        # then (0, 1), (0, 2), ...
        return all_anchors

    def valid_flags(self, featmap_size, valid_size, device='cuda'):
        feat_h, feat_w = featmap_size
        valid_h, valid_w = valid_size
        assert valid_h <= feat_h and valid_w <= feat_w
        valid_x = torch.zeros(feat_w, dtype=torch.bool, device=device)
        valid_y = torch.zeros(feat_h, dtype=torch.bool, device=device)
        valid_x[:valid_w] = 1
        valid_y[:valid_h] = 1
        valid_xx, valid_yy = meshgrid(valid_x, valid_y)
        valid = valid_xx & valid_yy
        valid = valid[:,
                      None].expand(valid.size(0),
                                   self.num_base_anchors).contiguous().view(-1)
        return valid
