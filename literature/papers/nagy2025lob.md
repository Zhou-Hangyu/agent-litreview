---
abstract: While financial data presents one of the most challenging and interesting sequence modelling tasks due to high noise, heavy tails, and strategic interactions, progress in this area has been hindered by the lack of consensus on quantitative evaluation paradigms. To address this, we present LOB-Bench, a benchmark, implemented in python, designed to evaluate the quality and realism of generative message-by-order data for limit order books (LOB) in the LOBSTER format. Our framework measures distributional differences in conditional and unconditional statistics between generated and real LOB data, supporting flexible multivariate statistical evaluation. The benchmark also includes features commonly used LOB statistics such as spread, order book volumes, order imbalance, and message inter-arrival times, along with scores from a trained discriminator network. Lastly, LOB-Bench contains"market impact metrics", i.e. the cross-correlations and price response functions for specific events in the data. We benchmark generative autoregressive state-space models, a (C)GAN, as well as a parametric LOB model and find that the autoregressive GenAI approach beats traditional model classes.
arxiv_id: '2502.09172'
authors:
- Nagy, Peer
- Frey, Sascha
- Li, Kang
- Sarkar, Bidipta
- Vyetrenko, Svitlana
- Zohren, Stefan
- Calinescu, Ani
- Foerster, Jakob
citation_count: 7
cited_by: []
cites:
- id: kawawa-beaudan2026tradefm
  type: surveys
- id: wheeler2024marketgpt
  type: surveys
- id: berti2025trades
  type: surveys
doc_id: nagy2025lob
doi: 10.48550/arXiv.2502.09172
et_al: false
influential_citation_count: 0
pdf_path: papers/2502.09172.pdf
reading_status:
  global: unread
related: []
resource_type: paper
s2_id: 80e111a3da98a87e170f797c6dee988871d78b1c
tags:
- limit order book
- benchmark
- generative models
- deep learning
themes: []
title: "LOB-Bench: Benchmarking Generative AI for Finance - an Application to Limit Order Book Data"
tldr: This work presents LOB-Bench, a benchmark, implemented in python, designed to evaluate the quality and realism of generative message-by-order data for limit order books (LOB) in the LOBSTER format, and finds that the autoregressive GenAI approach beats traditional model classes.
url: https://arxiv.org/abs/2502.09172
venue: International Conference on Machine Learning
year: 2025
---
## Notes

(Add your notes here)
