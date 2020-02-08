import argparse
import os
import random

import numpy as np
import torch
from google.colab import drive
from torch.utils.data import (DataLoader, TensorDataset, WeightedRandomSampler)
from tqdm import trange
from transformers import *

BATCH_SIZE = 10
WORK_DIR = '/content/drive/My Drive/Overig'
EPOCHS = 1


def unpack_batch(batch):
    input_ids = batch[0]
    attention_mask = batch[1]
    type_ids = batch[2]
    y_true = batch[3]
    return input_ids, attention_mask, type_ids, y_true


def create_dataloader_training(features):
    # The next lines are taken from the example at https://github.com/huggingface/transformers/blob/0cb163865a4c761c226b151283309eedb2b1ca4d/transformers/data/processors/glue.py#L30
    all_input_ids = torch.tensor([f.input_ids for f in features], dtype=torch.long)
    all_attention_mask = torch.tensor([f.attention_mask for f in features], dtype=torch.long)
    all_token_type_ids = torch.tensor([f.token_type_ids for f in features], dtype=torch.long)
    all_labels = torch.tensor([f.label for f in features], dtype=torch.long)

    dataset = TensorDataset(all_input_ids, all_attention_mask, all_token_type_ids, all_labels)

    class_counts = np.bincount(all_labels)
    class_sample_freq = 1 / class_counts
    weights = [class_sample_freq[label] for label in all_labels]
    print(class_counts)
    print(class_sample_freq)
    num_samples = round(class_counts[1] * 2).item()  # .item to convert to native int
    print(f'Num samples: {num_samples}')
    sampler = WeightedRandomSampler(weights, num_samples=num_samples,
                                    replacement=True)  # we want to use all positive instances and use equally as many negative instances. This should now generally happen by chance
    dataloader = DataLoader(dataset, sampler=sampler, batch_size=BATCH_SIZE)
    return dataloader


# Sorry for the bloated file, it was converted from a notebook
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--features', required=True)
    parser.add_argument('--samplenegative', default=True)

    args = parser.parse_args()
    drive.mount('/content/drive')

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_gpu = torch.cuda.device_count()
    torch.cuda.get_device_name(0)

    print("Load cached training features")
    cached_features_file_train = os.path.join(WORK_DIR, args.features)
    features_train = torch.load(cached_features_file_train)
    len(features_train)

    np.bincount(torch.tensor([f.label for f in features_train], dtype=torch.long))

    if args.samplenegative:
        new_features = []
        for f in features_train:
            if f.label == 1:
                new_features.append(f)
            else:
                # throw away 60% of neg instances at random
                if random.uniform(0, 1) < 0.5:
                    new_features.append(f)
        features_train = new_features

    len(features_train)

    torch.cuda.empty_cache()
    print("Create train dataloader")
    dataloader_train = create_dataloader_training(features_train)
    del features_train
    print(f"Len train dataloader: {len(dataloader_train)}")

    model = BertForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)
    model.cuda()
    pass  # suppress model.cuda output

    # This is a very standard piece of code for the optimizer parameters, available from many sources, e.g. https://worksheets.codalab.org/rest/bundles/0x60ed20fc419641d799f53aa0667d5713/contents/blob/basic_trainer.py
    param_optimizer = list(model.named_parameters())
    no_decay = ['bias', 'gamma', 'beta']
    optimizer_grouped_parameters = [
        {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)],
         'weight_decay_rate': 0.01},
        {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)],
         'weight_decay_rate': 0.0}
    ]

    optimizer = AdamW(optimizer_grouped_parameters,
                      lr=2e-5)

    train_loss_set = []

    # use trange for a prediction of the time it will take and to record execution times
    for _ in trange(EPOCHS, desc="Epoch"):

        # TRAINING ON TRAIN SET
        model.train()

        # Train the data for one epoch
        for step, batch in enumerate(dataloader_train):
            if step % 1000 == 0:
                print(f'\nAt step {step}')
            # Move batch to GPU
            batch = tuple(t.to(device) for t in batch)
            # Unpack values
            input_ids, attention_mask, type_ids, y_true = unpack_batch(batch)
            # Clear out the gradients (by default they accumulate) taken from https://mccormickml.com/2019/07/22/BERT-fine-tuning/
            optimizer.zero_grad()
            # Make predictions for the batch
            outputs = model(input_ids, token_type_ids=type_ids, attention_mask=attention_mask, labels=y_true)
            loss = outputs[0]
            train_loss_set.append(loss.item())
            loss.backward()  # Backpropagate
            optimizer.step()

    model.save_pretrained(WORK_DIR)
    print("Done!")

    with open(os.path.join(WORK_DIR, "losses.txt"), "w") as f:
        for loss in train_loss_set:
            f.write(f'{loss}\n')
