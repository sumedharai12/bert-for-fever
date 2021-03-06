import random

import numpy as np

from bert_for_fever.bert_model_wrapper import BertModelWrapper

BATCH_SIZE = 10


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


def sample_negative(features_train):
    """"Sample from the instances with a negative label."""
    new_features = []
    for f in features_train:
        if f.label == 1:
            new_features.append(f)
        else:
            # throw away 60% of neg instances at random
            if random.uniform(0, 1) < 0.5:
                new_features.append(f)
    return new_features


def train_model(cached_features_fname: str, sample_negative_instances: bool, work_dir: str):
    """Train a model on the featuers given in cached_features_file_train."""
    features_train = torch.load(cached_features_fname)
    if sample_negative_instances:
        features_train = sample_negative(features_train)
    torch.cuda.empty_cache()
    print("Create train dataloader")
    dataloader_train = create_dataloader_training(features_train)
    del features_train
    print(f"Len train dataloader: {len(dataloader_train)}")
    bert_model = BertModelWrapper()
    train_loss_set = bert_model.train(dataloader_train)
    bert_model.save(work_dir)
    return train_loss_set
