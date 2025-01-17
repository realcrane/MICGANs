# Unsupervised Image Generation with Infinite Generative Adversarial Networks

Here is the implementation of MICGANs using DCGAN architecture on MNIST dataset, now is accepted by ICCV 2021.

### Install Requirements

+ pytorch >= 1.3
+ packages in requirements.txt

### Training


First, for initialization stage training:

```
bash Scripts/mnist/train_initialization.sh
```

Then, for ACRP stage training:

```
bash Scripts/mnist/train_crp.sh
```

The above training is under the setting that mode number is 15.

### Visualization

During training, for the better understanding of CRP sampling procedure, we visualize the classification results of the real images on each state of the CRP sampling procedure. And the visulization results are in the 'output/mnist/crp/mode_label', 'output/mnist/crp/sorted_mode_label' and 'output/mnist/crp/label_mode'.

The images in the 'mode_label' are like the following:

![mode_label](images/mode_label.png)

In the image, the x-axis is the mode id, the y-axis is the number of the real images classified to the mode, and the color represents the ground-truth label. Images in the 'sorted_mode_label' shows the sorted results. For images in the 'label_mode', the x-axis the ground-truth label, and the color represents mode id.

### Notes

+ The CRP sampling procedure is at its core Markov Chain Monte Carlo (MCMC) sampling. Other than plotting the likelihood, another good way to see if it has mixed is to plot out the clustering results as the above image. Also, since it is MCMC, different samples could give slightly different results even after it mixes.
