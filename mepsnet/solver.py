import io
import numpy as np
import os
import time
import torch
import torch.nn as nn

from data import generate_loader
import utils

#from tensorboardX import SummaryWriter

class Solver():
    def __init__(self, module, opt):
        self.opt = opt

        if not opt.gpu:
            self.dev = torch.device("cpu")
        self.dev = torch.device(f"cuda:{opt.gpu}")

        self.net = module.Net(opt).to(self.dev)
        print("# Params: ", sum(map(lambda x: x.numel(), self.net.parameters())))

        if opt.pretrain:
            self.load(opt.pretrain)

        if opt.loss.lower() == 'mse':
            self.loss_fn = nn.MSELoss()
        elif opt.loss.lower() == 'l1':
            self.loss_fn = nn.L1Loss()
        else:
            raise ValueError(
                "ValueError - wrong type of loss function(need MSE or L1)")

        if not opt.test_only:
            self.train_loader = generate_loader("train", opt)
            self.valid_loader = generate_loader("valid", opt)
        self.test_loader = generate_loader("test", opt)

        self.optim = torch.optim.Adam(
            params=self.net.parameters(),
            lr=opt.lr,
            betas=(0.9, 0.999),
            eps=1e-8,
            weight_decay=opt.weight_decay
        )
        self.scheduler = torch.optim.lr_scheduler.MultiStepLR(
            optimizer=self.optim,
            milestones=[int(len(self.train_loader)*int(d)) for d in opt.decay.split("-")],
            gamma=0.5
        )  # milestones at 200th and 500th epochs

        self.t1, self.t2 = None, None
        self.best_psnr, self.best_epoch = 0, 0

#        self.writer = SummaryWriter(log_dir = './log')

    def fit(self):
        opt = self.opt

        self.t1 = time.time()

        ### NOT USED ###
#        for epoch in range(opt.max_epochs):
#            try:
#                inputs = next(iters)
#            except (UnboundLocalError, StopIteration):
#                iters = iter(self.train_loader)
#                inputs = next(iters)
        epoch = 1

        while epoch <= opt.max_epochs:
            for batch, (data, ref) in enumerate(self.train_loader):
                noisy_im = data.to(self.dev)
                clean_im = ref.to(self.dev)

                restore_im = self.net(noisy_im)

                loss = self.loss_fn(restore_im, clean_im)

                if not torch.isfinite(loss):
                    print(
                        'Warning: Losses are Nan, negative infinity, or infinity. Stop Training')
                    exit(1)

                print('[{}/{}] LOSS: {}'.format(epoch, batch+1, loss))
                self.optim.zero_grad()
                loss.backward()

                self.optim.step()
                self.scheduler.step()

#            self.writer.add_scalar('train/loss', total_loss, epoch)

            if epoch % opt.eval_epochs == 0:
                self.summary_and_save(epoch, self.valid_loader)
                
            epoch += 1

    def summary_and_save(self, epoch, loader):
        epoch, max_epochs = epoch, self.opt.max_epochs
        psnr = self.evaluate(loader)
        self.t2 = time.time()

        if psnr >= self.best_psnr:
            self.best_psnr, self.best_epoch = psnr, epoch
            self.save(epoch)

        curr_lr = self.scheduler.get_lr()[0]
        eta = (self.t2-self.t1) * (max_epochs-epoch) / 3600
        print("[{}K/{}K] {:.2f} (Best: {:.2f} @ {}K epochs) LR: {}, ETA: {:.1f} hours"
              .format(epoch, max_epochs, psnr, self.best_psnr, self.best_epoch,
                      curr_lr, eta))

        self.t1 = time.time()
#        self.writer.add_scalar('valid/psnr', psnr, epoch)

    @ torch.no_grad()
    def evaluate(self, loader):
        opt = self.opt
        self.net.eval()

        if opt.save_result:
            save_root = os.path.join(opt.save_root, opt.dataset)
            os.makedirs(save_root, exist_ok=True)

        psnr = 0

        for i, inputs in enumerate(loader):  # patch_list, target, filename
            clean_im = inputs[1].squeeze(0)
            filename = str(inputs[2])[2:-3]

            restore_patch = []
            for patch_idx, patch in enumerate(inputs[0]):
                patch = patch.to(self.dev).squeeze(0)
                outputs = self.net(patch).squeeze(0).clamp(
                    0, 255).round().cpu().byte().permute(1, 2, 0).numpy()
                restore_patch.append(outputs)

            # merge 8 restored patches
            h, w = clean_im.size()[1:]
            h_half, w_half = int(h/2), int(w/2)
            h_quarter, w_quarter = int(h_half/2), int(w_half/2)
            h_shave, w_shave = int(h_quarter/2), int(w_quarter/2)

            restore_im = np.ndarray((h, w, 3))

            restore_im[0:h_half, 0:w_quarter, :] = restore_patch[0][
                0:h_half, 0:w_quarter, :]
            restore_im[0:h_half, w_quarter:w_half, :] = restore_patch[1][
                0:h_half, 0:-w_shave, :]
            restore_im[0:h_half, w_half:w_half+w_quarter, :] = restore_patch[2][
                0:h_half, 0:w_quarter, :]
            restore_im[0:h_half, w_half+w_quarter:w, :] = restore_patch[3][
                0:h_half, w_shave:, :]
            restore_im[h_half:h, 0:w_quarter, :] = restore_patch[4][
                h_shave:, 0:w_quarter, :]
            restore_im[h_half:h, w_quarter:w_half, :] = restore_patch[5][
                h_shave:, 0:-w_shave, :]
            restore_im[h_half:h, w_half:w_half+w_quarter, :] = restore_patch[6][
                h_shave:, 0:w_quarter, :]
            restore_im[h_half:h, w_half+w_quarter:w, :] = restore_patch[7][
                h_shave:, w_shave:, :]

            clean_im = clean_im.cpu().byte().permute(1, 2, 0).numpy().astype(np.uint8)
            restore_im = restore_im.astype(np.uint8)

            if opt.save_result:
                save_path = os.path.join(save_root, f"{filename}")
                io.imsave(save_path, restore_im)

            psnr_tmp = utils.calculate_psnr(clean_im, restore_im)
            print(f'{i}th image PSNR: {psnr_tmp}')
            psnr += psnr_tmp
            self.net.train()

        return psnr/len(loader)


    def load(self, path):
        state_dict = torch.load(
            path, map_location=lambda storage, loc: storage)

        if self.opt.strict_load:
            self.net.load_state_dict(state_dict)
        return

        own_state = self.net.state_dict()
        for name, param in state_dict.items():
            if name in own_state:
                if isinstance(param, nn.Parameter):
                    param = param.data

                try:
                    own_state[name].copy_(param)
                except Exception:
                    # head and tail modules can be different
                    if name.find("head") == -1 and name.find("tail") == -1:
                        raise RuntimeError(
                            "While copying the parameter named {}, "
                            "whose dimensions in the model are {} and "
                            "whose dimensions in the checkpoint are {}."
                            .format(name, own_state[name].size(), param.size())
                        )
            else:
                raise RuntimeError(
                    "Missing key {} in model's state_dict".format(name)
                )

    def save(self, epoch):
        os.makedirs(self.opt.ckpt_root, exist_ok=True)
        save_path = os.path.join(self.opt.ckpt_root, str(epoch)+".pt")
        torch.save(self.net.state_dict(), save_path)
