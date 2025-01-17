import torch
import numpy as np
import random
from sklearn.decomposition import PCA

def choice_sample(prob_list, batch=1):
    if prob_list.sum() == 0:
        picked_id = np.random.randint(low=0, high=len(prob_list), size=batch)
    else:
        prob_list = prob_list.copy()
        for i in range(1, len(prob_list)):
            prob_list[i] = prob_list[i-1] + prob_list[i]
        prob_sum = prob_list[-1]
        rand_nums = np.random.rand(batch) * prob_sum
        picked_id = (prob_list[None, :] < rand_nums[:, None]).sum(axis=1)
    return picked_id

class Clusterer():
    def __init__(self, num_k, multi_gauss, epoch_1, epoch_2, **kwargs):
        self.num_k = num_k
        self.multi_gauss = multi_gauss
        self.epoch_1 = epoch_1
        self.epoch_2 = epoch_2
        self.distribution = torch.ones(num_k) / num_k

        self.picked_class = None

    def get_labels(self, index):
        if self.picked_class is None:
            return None
        else:
            return self.picked_class[index]

    def sample_y(self, batch_size):
        m = torch.distributions.Categorical(self.distribution)

        y = torch.zeros(batch_size).long().cuda()
        for i in range(batch_size):
            y[i] = m.sample()
        return y

    def crp_sample(self, likelihoods, sample_iter, type="old", save_mid_conds=False):
        image_num, K_num = likelihoods.shape
        likelihoods = likelihoods / likelihoods.max(dim=1)[0].unsqueeze(1)

        mid_conds = []
        if K_num == 1:
            picked_class = torch.zeros(image_num).long()
            return picked_class
        else:
            picked_class = torch.argmax(likelihoods, dim=1)
        if save_mid_conds:
            mid_conds.append(picked_class.clone().detach())

        if type == "old":
            for _ in range(sample_iter):
                k_counts = torch.zeros(K_num)
                for k in range(K_num):
                    k_counts[k] = (picked_class == k).sum()

                count_prior = k_counts
                post_prob = count_prior[None, :] * likelihoods
                post_prob = post_prob.numpy()
                for im in range(len(post_prob)):
                    picked_class[im] = torch.tensor(choice_sample(post_prob[im])[0])
                
                if save_mid_conds:
                    mid_conds.append(picked_class.clone().detach())
        else:
            k_counts = torch.zeros(K_num)
            for k in range(K_num):
                k_counts[k] = (picked_class == k).sum()

            for _ in range(sample_iter):
                rand_ids = list(range(image_num))
                random.shuffle(rand_ids)
                for im in rand_ids:
                    k_counts[picked_class[im]] -= 1
                    post_prob = k_counts * likelihoods[im]
                    post_prob = post_prob.numpy()
                    picked_class[im] = torch.tensor(choice_sample(post_prob)[0])
                    k_counts[picked_class[im]] += 1
                if save_mid_conds:
                    mid_conds.append(picked_class.clone().detach())

        return picked_class, mid_conds

    def crp(self, embeddings, record=False, dim_reduce=False):
        mid_results_epochs = []
        record_multi_gauss = []

        if record:
            gauss_dict = {
                'mean': self.multi_gauss.mean.cpu().numpy(),
                'sigma_det_recip': self.multi_gauss.sigma_det_recip.cpu().numpy(),
                'sigma_inverse': self.multi_gauss.sigma_inverse.cpu().numpy(),
                'sigma_det_recip_scalor': self.multi_gauss.sigma_det_recip_scalor.cpu().numpy()
            }
            record_multi_gauss.append(gauss_dict)

        for e1 in range(self.epoch_1):
            # compute likelihood
            likelyhood_ims = torch.zeros(embeddings.shape[0], self.num_k)
            start = 0
            step = 128
            while start < embeddings.shape[0]:
                end = min(start + step, embeddings.shape[0])
                if dim_reduce:
                    probs, log_probs = self.multi_gauss.compute_embed_probs_reduce(embeddings[start:end])
                else:
                    probs, log_probs = self.multi_gauss.compute_embed_probs(embeddings[start:end])
                likelyhood_ims[start:end] = probs.cpu()

                start = start + step

            # reduce dim to prevent numerical problem
            if dim_reduce and e1 == 0:
                self.multi_gauss.pca_transform(embeddings)

            # crp sample
            picked_class, mid_results = self.crp_sample(likelyhood_ims, sample_iter=self.epoch_2, type="new", save_mid_conds=True)
            mid_results_epochs.append(mid_results)

            # collect clustered embeddings
            embedding_list = []
            for k in range(self.num_k):
                valid = picked_class == k
                embedding_list.append(embeddings[valid])

            # self.main_components(embedding_list)
            # update gaussian model
            if dim_reduce:
                self.multi_gauss.update_reduce(embedding_list)
            else:
                self.multi_gauss.update(embedding_list)

            if record:
                gauss_dict = {
                    'mean': self.multi_gauss.mean.cpu().numpy(),
                    'sigma_det_recip': self.multi_gauss.sigma_det_recip.cpu().numpy(),
                    'sigma_inverse': self.multi_gauss.sigma_inverse.cpu().numpy(),
                    'sigma_det_recip_scalor': self.multi_gauss.sigma_det_recip_scalor.cpu().numpy()
                }
                record_multi_gauss.append(gauss_dict)

            # update removed picked class
            removed_list = self.multi_gauss.get_remove_list()
            keep_list = [i for i in range(self.num_k) if i not in removed_list]
            keep_list = np.array(keep_list)
            for k in removed_list:
                is_removed = picked_class == k
                if is_removed.sum() > 0:
                    random_ids = choice_sample(np.zeros([len(keep_list)]), is_removed.sum().item())
                    picked_class[is_removed] = torch.tensor(keep_list[random_ids])
            # for k in removed_list:
            #     is_removed = picked_class == k
            #     if is_removed.sum() > 0:
            #         removed_embeddings = embeddings[is_removed]
            #         if dim_reduce:
            #             probs, log_probs = self.multi_gauss.compute_embed_probs_reduce(removed_embeddings)
            #         else:
            #             probs, log_probs = self.multi_gauss.compute_embed_probs(removed_embeddings)
            #         picked_class[is_removed] = torch.argmax(log_probs, dim=1).cpu()

        # update distribution
        k_counts = torch.zeros(self.num_k)
        for k in range(self.num_k):
            k_counts[k] = (picked_class == k).sum()
        self.distribution = k_counts / k_counts.sum()

        self.picked_class = picked_class

        return mid_results_epochs, record_multi_gauss
    
    def main_components(self, embeddings):
        variance_ratios = {}
        n_components = 3
        for i in range(len(embeddings)):
            X = embeddings[i].cpu().numpy()
            if len(X) > 100:
                pca = PCA(n_components=n_components)
                pca.fit(X)
                variance_ratios[i] = pca.explained_variance_ratio_

        print(variance_ratios)