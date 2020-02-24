import math
import torch
import torch.nn as nn

class Conv_ReLU_Block(nn.Module):
    def __init__(self):
        super(Conv_ReLU_Block, self).__init__()
        self.body = nn.Sequential(nn.Conv2d(in_channels=64,
                                            out_channels=64,
                                            kernel_size=3,
                                            stride=1,
                                            padding=1,
                                            bias=False),
                                  nn.ReLU(inplace=True))
  
    def forward(self, x):
        output = self.body(x)
        return output

class VDSRNet(nn.Module):
    def __init__(self, num_blocks=21, num_experts=1):
        super(VDSRNet, self).__init__()
        self.residual_layer = self.make_layer(Conv_ReLU_Block, num_of_layer=num_blocks * num_experts)

        self.input = nn.Conv2d(in_channels=3, 
                               out_channels=64,
                               kernel_size=3, 
                               stride=1, 
                               padding=1, 
                               bias=False)
        self.output = nn.Conv2d(in_channels=64, 
                                out_channels=3, 
                                kernel_size=3, 
                                stride=1, 
                                padding=1, 
                                bias=False)
        self.relu = nn.ReLU(inplace=True)


        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))


    def make_layer(self, block, num_of_layer):
        layers = []
        for _ in range(num_of_layer):
            layers.append(block())
        return nn.Sequential(*layers)

    def forward(self, x):
        residual = x
        output = self.relu(self.input(x))
        output = self.residual_layer(output)
        output = self.output(output)
        out = torch.add(out, residual)
        return out

    def __repr__(self):
        return f"{self.__module__.split('.')[-1].upper()} " \
            f"<{self.__class__.__name__}>"