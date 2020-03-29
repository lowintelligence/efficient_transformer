import torch
import torch.nn as nn
from playground.Layers import EncoderLayer, DecoderLayer
from playground.Embed import Embedder, PositionalEncoder
from playground.Sublayers import Norm
from torch.nn import functional as F
import copy


def get_clones(module, N):
    return nn.ModuleList([copy.deepcopy(module) for i in range(N)])


class Encoder(nn.Module):
    def __init__(self, vocab_size, d_model, N, heads, dropout):
        super().__init__()
        self.N = N
        self.embed = Embedder(vocab_size, d_model)
        self.pe = PositionalEncoder(d_model, dropout=dropout)
        self.layers = get_clones(EncoderLayer(d_model, heads, dropout), N)
        self.norm = Norm(d_model)

    def forward(self, src, mask):
        x = self.embed(src)
        x = self.pe(x)
        for i in range(self.N):
            x = self.layers[i](x, mask)
        return self.norm(x)


class Decoder(nn.Module):
    def __init__(self, vocab_size, d_model, N, heads, dropout, is_lm=True):
        super().__init__()
        self.N = N
        self.embed = Embedder(vocab_size, d_model)
        self.pe = PositionalEncoder(d_model, dropout=dropout)
        self.layers = get_clones(DecoderLayer(d_model, heads, dropout, is_lm=is_lm), N)
        self.norm = Norm(d_model)

    def forward(self, trg, e_outputs, src_mask, trg_mask, is_lm=True):
        x = self.embed(trg)
        x = self.pe(x)
        for i in range(self.N):
            if is_lm:
                assert not e_outputs
            x = self.layers[i](x, e_outputs, src_mask, trg_mask, is_lm)  # is_lm, e_outputs is expected to be None
        return self.norm(x)


class Transformer(nn.Module):
    # is_lm stands for is a Language Model --> Transformer without the encoder
    def __init__(self, src_vocab, trg_vocab, d_model, N, heads, dropout, is_lm=True):
        super().__init__()
        if not is_lm:
            self.encoder = Encoder(src_vocab, d_model, N, heads, dropout)
        self.decoder = Decoder(trg_vocab, d_model, N, heads, dropout, is_lm=is_lm)
        self.out = nn.Linear(d_model, trg_vocab)

    def forward(self, src, trg, src_mask, trg_mask, is_lm=True):
        if is_lm:
            e_outputs = None
        else:
            e_outputs = self.encoder(src, src_mask)
        d_output = self.decoder(trg, e_outputs, src_mask, trg_mask, is_lm)
        output = self.out(d_output)
        # softmax layer
        output = F.log_softmax(output, dim=-1)  # along the embedding (d_model) dimension
        return output


def get_model(opt, src_vocab, trg_vocab):
    assert opt.d_model % opt.heads == 0
    assert opt.dropout < 1

    model = Transformer(src_vocab, trg_vocab, opt.d_model, opt.n_layers, opt.heads, opt.dropout)

    if opt.load_weights is not None:
        print("loading pretrained weights...")
        model.load_state_dict(torch.load(f'{opt.load_weights}/model_weights'))
    else:
        for p in model.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    if opt.device == 0:
        model = model.cuda()

    return model