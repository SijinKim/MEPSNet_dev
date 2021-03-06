import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import init


class TemplateBank(nn.Module):
    def __init__(self, num_templates, in_planes, out_planes, kernel_size):
        super(TemplateBank, self).__init__()

        self.coefficient_shape = (num_templates, 1, 1, 1, 1)
        templates = [torch.Tensor(
            out_planes, in_planes, kernel_size, kernel_size) for _ in range(num_templates)]
        for i in range(num_templates):
            init.kaiming_normal_(templates[i])
        self.templates = nn.Parameter(torch.stack(templates))

    def forward(self, coefficients):
        return (self.templates * coefficients).sum(0)


class SConv2d(nn.Module):
    def __init__(self, bank, stride=1, padding=1, dilation=1):
        super(SConv2d, self).__init__()

        self.stride = stride
        self.padding = padding
        self.bank = bank
        self.dilation = dilation
        self.coefficients = nn.Parameter(torch.zeros(bank.coefficient_shape))

    def forward(self, input):
        params = self.bank(self.coefficients)
        return F.conv2d(input, params, stride=self.stride, padding=self.padding, dilation=self.dilation)


class SResidualBlock(nn.Module):
    def __init__(self, bank):
        super(SResidualBlock, self).__init__()

        body = [
            SConv2d(bank, 1, 1, 1),
            nn.ReLU(inplace=True),
            SConv2d(bank, 1, 1, 1)
        ]

        self.body = nn.Sequential(*body)

    def forward(self, x):
        res = self.body(x)
        res += x
        return res


class SRIR(nn.Module):
    def __init__(self, bank, num_SResidualBlocks=12):
        super(SRIR, self).__init__()

        body = list()
        for _ in range(num_SResidualBlocks):
            body += [SResidualBlock(bank)]

        self.body = nn.Sequential(*body)

    def forward(self, x):
        res = self.body(x)
        res += x
        return res
