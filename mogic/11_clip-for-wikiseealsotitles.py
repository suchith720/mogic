# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/11_clip-for-wikiseealsotitles.ipynb.

# %% auto 0
__all__ = ['CLIP001']

# %% ../nbs/11_clip-for-wikiseealsotitles.ipynb 2
import os,torch, torch.multiprocessing as mp, pickle, numpy as np, math, transformers

from transformers import CLIPTextModel
import torch.nn.functional as F

from xcai.basics import *
from xcai.models.modeling_utils import *
from xcai.losses import *

from xclib.utils.sparse import retain_topk

from fastcore.utils import *

# %% ../nbs/11_clip-for-wikiseealsotitles.ipynb 4
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1'
os.environ['WANDB_PROJECT']='oakI_00-wikiseealsotitles'

# %% ../nbs/11_clip-for-wikiseealsotitles.ipynb 8
class CLIP001(CLIPTextModel):

    def __init__(
        self, 
        config,
        num_batch_labels:Optional[int]=None, 
        batch_size:Optional[int]=None,
        margin:Optional[float]=0.3,
        num_negatives:Optional[int]=5,
        tau:Optional[float]=0.1,
        apply_softmax:Optional[bool]=True,
    ):
        super().__init__(config)
        self.loss_fn = MultiTriplet(bsz=batch_size, tn_targ=num_batch_labels, margin=margin, n_negatives=num_negatives, 
                                    tau=tau, apply_softmax=apply_softmax, reduce='mean')

    def compute_loss(self, inp_repr, targ_repr, targ_ptr, targ_idx, ptarg_ptr, ptarg_idx):
        return self.loss_fn(inp_repr, targ_repr, targ_ptr, targ_idx, ptarg_ptr, ptarg_idx)

    def encode(self, input_ids:torch.Tensor, attention_mask:torch.Tensor, **kwargs):
        o = self.text_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            **kwargs
        )
        return F.normalize(Pooling.mean_pooling(o[0], attention_mask), dim=1)

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
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        **kwargs
    ):  
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        data_rep = self.encode(data_input_ids, data_attention_mask)
        
        loss = None; lbl2data_rep = None
        if lbl2data_input_ids is not None:
            lbl2data_rep = self.encode(lbl2data_input_ids, lbl2data_attention_mask)
            
            loss = self.compute_loss(data_rep, lbl2data_rep,lbl2data_data2ptr,lbl2data_idx,
                                     plbl2data_data2ptr,plbl2data_idx)
            
        return XCModelOutput(
            loss=loss,
            data_repr=data_rep,
            lbl2data_repr=lbl2data_rep,
        )
        

# %% ../nbs/11_clip-for-wikiseealsotitles.ipynb 13
if __name__ == '__main__':
    build_block = True
    pkl_dir = '/home/scai/phd/aiz218323/scratch/datasets/'
    data_dir = '/home/scai/phd/aiz218323/Projects/XC_NLG/data'
    
    output_dir = '/home/scai/phd/aiz218323/scratch/outputs/mogic/11_clip-for-wikiseealsotitles'
    
    """ Load data """
    pkl_file = f'{pkl_dir}/processed/wikiseealsotitles_data_openai-clip-vit-base-patch32_xcs.pkl'

    if build_block:
        block = XCBlock.from_cfg(data_dir, 'data', transform_type='xcs', tokenizer='openai/clip-vit-base-patch32', 
                                 sampling_features=[('lbl2data',1)], oversample=False)
        with open(pkl_file, 'wb') as file: pickle.dump(block, file)
        exit()
    else:
        with open(pkl_file, 'rb') as file: block = pickle.load(file)

    block.collator.tfms.tfms[0].sampling_features = [('lbl2data',1)]
    block.collator.tfms.tfms[0].oversample = False

    """ Training arguements """
    args = XCLearningArguments(
        output_dir=output_dir,
        logging_first_step=True,
        per_device_train_batch_size=800,
        per_device_eval_batch_size=800,
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
        
        prune_metadata=False,
        num_metadata_prune_warmup_epochs=10,
        num_metadata_prune_epochs=5,
        metadata_prune_batch_size=2048,
        prune_metadata_names=['lnk_meta'],
        use_data_metadata_for_pruning=True,
    
        predict_with_augmentation=False,
        use_augmentation_index_representation=False,
    
        data_aug_meta_name='lnk',
        augmentation_num_beams=None,
        data_aug_prefix='lnk',
        use_label_metadata=False,
        
        data_meta_batch_size=2048,
        augment_metadata=False,
        num_metadata_augment_warmup_epochs=10,
        num_metadata_augment_epochs=5,
    
        use_cpu_for_searching=False,
        use_cpu_for_clustering=True,
    )

    """ model """
    bsz = max(args.per_device_train_batch_size, args.per_device_eval_batch_size)*torch.cuda.device_count()
    model = CLIP001.from_pretrained('sentence-transformers/msmarco-distilbert-base-v4', batch_size=100, num_batch_labels=5000, 
                                    margin=0.3, num_negatives=10, tau=0.1, apply_softmax=True)
    
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
    
    print(learn.evaluate())
    