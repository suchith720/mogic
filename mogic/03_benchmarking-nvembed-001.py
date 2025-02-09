# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03_benchmarking_nvembed_bm25.ipynb.

# %% auto 0
__all__ = ['pkl_dir', 'data_dir', 'output_dir', 'pkl_file', 'block', 'input_text', 'tokenized_text', 'model', 'o', 'prompt_func',
           'RepresentationHead', 'NVM0XXEncoder', 'NVM009']

# %% ../nbs/03_benchmarking_nvembed_bm25.ipynb 2
import os,torch, torch.multiprocessing as mp, pickle, numpy as np, math, transformers
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

from xcai.basics import *

from xclib.utils.sparse import retain_topk

from fastcore.utils import *

# %% ../nbs/03_benchmarking_nvembed_bm25.ipynb 4
os.environ['CUDA_VISIBLE_DEVICES'] = '2,3,4,5'
os.environ['WANDB_PROJECT']='oakVn_00-wikiseealsotitles'
os.environ['WANDB_MODE'] = 'disabled'

from contextlib import nullcontext
from xcai.models.modeling_nvembed import NVEmbedModel
from transformers.activations import get_activation

import torch.nn as nn
from xcai.losses import MultiTriplet

from xcai.models.modeling_utils import XCModelOutput, Pooling

from fastcore.meta import *

# %% ../nbs/03_benchmarking_nvembed_bm25.ipynb 34
class RepresentationHead(torch.nn.Module):
    
    def __init__(self, config):
        super().__init__()
        self.transform = nn.Linear(config.hidden_size, config.hidden_size)
        self.layer_norm = nn.LayerNorm(config.hidden_size)
        self.projector = nn.Linear(config.hidden_size, config.hidden_size)
        self.activation = get_activation('relu')
        
        self.post_init()
        
    def post_init(self):
        torch.nn.init.eye_(self.transform.weight)
        torch.nn.init.eye_(self.projector.weight)

        torch.nn.init.zeros_(self.transform.bias)
        torch.nn.init.zeros_(self.projector.bias)
        
    def forward(self, x:torch.Tensor):
        x = self.transform(x)
        x = self.activation(x)
        x = self.layer_norm(x)
        x = self.projector(x)
        return x
        

# %% ../nbs/03_benchmarking_nvembed_bm25.ipynb 35
class NVM0XXEncoder(NVEmbedModel):
    
    def __init__(self, config, **kwargs):
        super().__init__(config)
        self.dr_head = RepresentationHead(config)
        
    @delegates(NVEmbedModel.__call__)
    def forward(
        self, 
        input_ids:Optional[torch.Tensor]=None, 
        attention_mask:Optional[torch.Tensor]=None,
        pool_mask: Optional[torch.Tensor]=None,
        return_dict: bool=True,
        **kwargs
    ):
        outputs = self.embedding_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )
        embeds = self.latent_attention_model(
            outputs.last_hidden_state,
            pool_mask,
        )
        rep = self.dr_head(embeds)
        return outputs, F.normalize(Pooling.mean_pooling(rep, attention_mask), dim=1)
    

# %% ../nbs/03_benchmarking_nvembed_bm25.ipynb 36
class NVM009(NVEmbedModel):
    use_generation,use_representation = False,True
    _tied_weights_keys = ["encoder.embedding_model,encoder.latent_attention_model"]
    
    def __init__(self,
                 config,
                 bsz:Optional[int]=None,
                 tn_targ:Optional[int]=None,
                 margin:Optional[float]=0.3,
                 tau:Optional[float]=0.1,
                 apply_softmax:Optional[bool]=False,
                 n_negatives:Optional[int]=5,
                 use_encoder_parallel:Optional[bool]=True,
                 *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        store_attr('use_encoder_parallel')
        self.encoder = NVM0XXEncoder(config)
        self.loss_fn = MultiTriplet(bsz=bsz, tn_targ=tn_targ, margin=margin, n_negatives=n_negatives, tau=tau, 
                                    apply_softmax=apply_softmax, reduce='mean')
        self.post_init()
        self.remap_post_init()
        
    def init_dr_head(self):
        self.encoder.dr_head.post_init()
        
    def remap_post_init(self):
        self.embedding_model = self.encoder.embedding_model
        self.latent_attention_model = self.encoder.latent_attention_model
    
    def forward(
        self,
        data_input_ids:Optional[torch.Tensor]=None,
        data_attention_mask:Optional[torch.Tensor]=None,
        lbl2data_data2ptr:Optional[torch.Tensor]=None,
        lbl2data_idx:Optional[torch.Tensor]=None,
        lbl2data_input_ids:Optional[torch.Tensor]=None,
        lbl2data_attention_mask:Optional[torch.Tensor]=None,
        plbl2data_data2ptr:Optional[torch.Tensor]=None,
        plbl2data_idx:Optional[torch.Tensor]=None,
        return_dict: Optional[bool] = None,
        **kwargs
    ):
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict
        
        if self.use_encoder_parallel: 
            encoder = nn.DataParallel(module=self.encoder)
        else: encoder = self.encoder
        
        data_o, data_repr = encoder(data_input_ids, data_attention_mask)
        
        loss, lbl2data_repr = None, None
        if lbl2data_input_ids is not None:
            lbl2data_o, lbl2data_repr = encoder(lbl2data_input_ids, lbl2data_attention_mask)
            
            loss = self.loss_fn(data_repr, lbl2data_repr, lbl2data_data2ptr, lbl2data_idx, 
                                plbl2data_data2ptr, plbl2data_idx, **kwargs)

        if not return_dict:
            o = (data_repr, lbl2data_repr)
            return ((loss,) + o) if loss is not None else o

        return XCModelOutput(
            loss=loss,
            data_repr=data_repr,
            lbl2data_repr=lbl2data_repr,
        )

if __name__ == '__main__':
    build_block = False
    pkl_dir = '/home/aiscuser/scratch1/datasets/'
    data_dir = '/data/datasets/'
    
    pkl_file = f'{pkl_dir}/processed/wikiseealsotitles_data_nv-embed-v2_xcs.pkl'
    
    if build_block:
        block = XCBlock.from_cfg(data_dir, 'data', transform_type='xcs', tokenizer='nvidia/NV-Embed-v2', 
                                 sampling_features=[('lbl2data',1)], max_sequence_length=64, oversample=False)
        
        def prompt_func(x):
            return f'''Instruct: Given the title of a wikipedia article, your task is to predict the titles of all articles which are \
        likely to be listed in the see also section of the mentioned article.\nQuery: {x}'''

        tokenizer = AutoTokenizer.from_pretrained('nvidia/NV-Embed-v2')
            
        input_text = [prompt_func(o) for o in block.train.dset.data.data_info['input_text']]
        tokenized_text = tokenizer.batch_encode_plus(input_text, truncation=True, max_length=64)
        block.train.dset.data.data_info.update(tokenized_text)
        
        input_text = [prompt_func(o) for o in block.test.dset.data.data_info['input_text']]
        tokenized_text = tokenizer.batch_encode_plus(input_text, truncation=True, max_length=64)
        block.test.dset.data.data_info.update(tokenized_text)
        
        with open(pkl_file, 'wb') as file: pickle.dump(block, file)
        exit()
    else:
        with open(pkl_file, 'rb') as file: block = pickle.load(file)
    
    
    model = NVM009.from_pretrained('nvidia/NV-Embed-v2', bsz=1024, margin=0.3, tau=0.1, n_negatives=10, apply_softmax=True, 
                                   use_encoder_parallel=False)
    
    batch = next(iter(block.train.dl))
    b = prepare_batch(model, batch)

    mode = model.to('cuda')
    b = b.to('cuda')

    with torch.no_grad():
        import pdb; pdb.set_trace()
        o = model(**b)

    print(o.loss)
