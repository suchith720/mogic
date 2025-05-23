# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03_benchmarking-nvembed.ipynb.

# %% auto 0
__all__ = ['prompt_func']

# %% ../nbs/03_benchmarking-nvembed.ipynb 2
import os,torch, torch.multiprocessing as mp, pickle, numpy as np, math, transformers
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

from xcai.basics import *
from xcai.models.NVM0XX import NVM009

from xclib.utils.sparse import retain_topk

from fastcore.utils import *

# %% ../nbs/03_benchmarking-nvembed.ipynb 4
os.environ['CUDA_VISIBLE_DEVICES'] = '2,3,4,5'
os.environ['WANDB_PROJECT']='oakVn_00-wikiseealsotitles'
os.environ['WANDB_MODE'] = 'disabled'

from scipy import sparse
from tqdm.auto import tqdm
from typing import List

@patch
def augment(self:AugmentMetaInputIdsTfm, data_ids:List, data_meta:sparse.csr_matrix, meta_ids:List):
    meta2data_ids = []
    for d_ids, d_meta in tqdm(zip(data_ids, data_meta), total=len(data_ids)):
        m2d_ids, sep_tok = d_ids[:-1].copy() if self.exclude_sep else d_ids.copy(), d_ids[-1:]
        for o in d_meta.indices[np.random.permutation(len(d_meta.indices))]:
            if self.exclude_sep: m2d_ids.extend(meta_ids[o][1:-1])
            else: m2d_ids.extend(meta_ids[o][1:])
            if self.max_len is not None and len(m2d_ids)>=self.max_len: m2d_ids = m2d_ids[:self.max_len]; break
        meta2data_ids.append(m2d_ids)
    return meta2data_ids

# %% ../nbs/03_benchmarking-nvembed.ipynb 34
def prompt_func(x):
    return f'''Instruct: Given the title of a wikipedia article, your task is to predict the titles of all articles which are \
likely to be listed in the see also section of the mentioned article.\nQuery: {x}'''

# %% ../nbs/03_benchmarking-nvembed.ipynb 35
if __name__ == '__main__':
    build_block = False
    pkl_dir = '/home/aiscuser/scratch1/datasets/'
    data_dir = '/data/datasets/'
    
    output_dir = '/home/aiscuser/scratch1/outputs/mogic/03_benchmarking-nvembed-002'

    """ Load data """
    pkl_file = f'{pkl_dir}/processed/wikiseealsotitles_data-meta_nv-embed-v2_xcs_cat-128.pkl'

    if build_block:
        block = XCBlock.from_cfg(data_dir, 'data_meta', transform_type='xcs', tokenizer='nvidia/NV-Embed-v2', 
                                 sampling_features=[('lbl2data',1)], max_sequence_length=16, oversample=False)

        tokenizer = AutoTokenizer.from_pretrained('nvidia/NV-Embed-v2')

        input_text = [prompt_func(o) for o in block.train.dset.data.data_info['input_text']]
        tokenized_text = tokenizer.batch_encode_plus(input_text, truncation=True, max_length=64)
        block.train.dset.data.data_info.update(tokenized_text)
        
        input_text = [prompt_func(o) for o in block.test.dset.data.data_info['input_text']]
        tokenized_text = tokenizer.batch_encode_plus(input_text, truncation=True, max_length=64)
        block.test.dset.data.data_info.update(tokenized_text)

        block = AugmentMetaInputIdsTfm.apply(block, 'cat_meta', 'data', 128, False)
        block = AugmentMetaInputIdsTfm.apply(block, 'cat_meta', 'lbl', 128, False)

        with open(pkl_file, 'wb') as file: pickle.dump(block, file)
        exit()
    else:
        with open(pkl_file, 'rb') as file: block = pickle.load(file)

    block.train.dset.data.data_info['input_ids'] = block.train.dset.data.data_info['input_ids_aug_cat']
    block.train.dset.data.data_info['attention_mask'] = block.train.dset.data.data_info['attention_mask_aug_cat']
    block.test.dset.data.data_info['input_ids'] = block.test.dset.data.data_info['input_ids_aug_cat']
    block.test.dset.data.data_info['attention_mask'] = block.test.dset.data.data_info['attention_mask_aug_cat']

    block.train.dset.data.lbl_info['input_ids'] = block.train.dset.data.lbl_info['input_ids_aug_cat']
    block.train.dset.data.lbl_info['attention_mask'] = block.train.dset.data.lbl_info['attention_mask_aug_cat']
    block.test.dset.data.lbl_info['input_ids'] = block.test.dset.data.lbl_info['input_ids_aug_cat']
    block.test.dset.data.lbl_info['attention_mask'] = block.test.dset.data.lbl_info['attention_mask_aug_cat']

    block.train.dset.meta = {}
    block.test.dset.meta = {}

    """ Training arguements """
    args = XCLearningArguments(
        output_dir=output_dir,
        logging_first_step=True,
        per_device_train_batch_size=25,
        per_device_eval_batch_size=25,
        representation_num_beams=200,
        representation_accumulation_steps=10,
        save_strategy="steps",
        evaluation_strategy="steps",
        eval_steps=5000,
        save_steps=5000,
        save_total_limit=5,
        num_train_epochs=300,
        predict_with_representation=True,
        adam_epsilon=1e-6,
        warmup_steps=100,
        weight_decay=0.01,
        learning_rate=2e-4,
        representation_search_type='BRUTEFORCE',
        
        output_representation_attribute='data_repr',
        label_representation_attribute='data_repr',
        metadata_representation_attribute='data_repr',
        data_augmentation_attribute='data_repr',
        representation_attribute='data_repr',
        clustering_representation_attribute='data_repr',
    
        group_by_cluster=True,
        num_clustering_warmup_epochs=10,
        num_cluster_update_epochs=5,
        num_cluster_size_update_epochs=25,
        use_data_metadata_for_clustering=True,
        clustering_type='EXPO',
        minimum_cluster_size=2,
        maximum_cluster_size=1600,

        metric_for_best_model='P@1',
        load_best_model_at_end=True,
        target_indices_key='plbl2data_idx',
        target_pointer_key='plbl2data_data2ptr',
        
        use_distributional_representation=False,
        use_encoder_parallel=True,
        max_grad_norm=None, 
        fp16=True,
        
        label_names=['lbl2data_idx', 'lbl2data_input_ids', 'lbl2data_attention_mask'],
    
        predict_with_augmentation=False,
        use_augmentation_index_representation=True,
    
        use_cpu_for_searching=False,
        use_cpu_for_clustering=True,
    )

    """ model """
    bsz = max(args.per_device_train_batch_size, args.per_device_eval_batch_size)*torch.cuda.device_count()
    model = NVM009.from_pretrained('nvidia/NV-Embed-v2', bsz=bsz, margin=0.3, tau=0.1, n_negatives=10, apply_softmax=True, 
                                   use_encoder_parallel=True)
    
    model.encoder.dr_head.activation = torch.nn.Identity()
    model.init_dr_head()
    
    """ Training """
    metric = PrecRecl(block.n_lbl, block.test.data_lbl_filterer, prop=block.train.dset.data.data_lbl,
                      pk=10, rk=200, rep_pk=[1, 3, 5, 10], rep_rk=[10, 100, 200])

    learn = XCLearner(
        model=model, 
        args=args,
        train_dataset=block.train.dset,
        eval_dataset=block.test.dset,
        data_collator=block.collator,
        compute_metrics=metric,
    )
    
    # mp.freeze_support()
    # learn.train()

    print(learn.evaluate())
