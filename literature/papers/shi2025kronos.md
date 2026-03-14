---
abstract: The success of large-scale pre-training paradigm, exemplified by Large Language Models (LLMs), has inspired the development of Time Series Foundation Models (TSFMs). However, their application to financial candlestick (K-line) data remains limited, often underperforming non-pre-trained architectures. Moreover, existing TSFMs often overlook crucial downstream tasks such as volatility prediction and synthetic data generation. To address these limitations, we propose Kronos, a unified, scalable pre-training framework tailored to financial K-line modeling. Kronos introduces a specialized tokenizer that discretizes continuous market information into token sequences, preserving both price dynamics and trade activity patterns. We pre-train Kronos using an autoregressive objective on a massive, multi-market corpus of over 12 billion K-line records from 45 global exchanges, enabling it to learn nuanced temporal and cross-asset representations. Kronos excels in a zero-shot setting across a diverse set of financial tasks. On benchmark datasets, Kronos boosts price series forecasting RankIC by 93% over the leading TSFM and 87% over the best non-pre-trained baseline. It also achieves a 9% lower MAE in volatility forecasting and a 22% improvement in generative fidelity for synthetic K-line sequences. These results establish Kronos as a robust, versatile foundation model for end-to-end financial time series analysis. Our pre-trained model is publicly available at https://github.com/shiyu-coder/Kronos.
arxiv_id: '2508.02739'
authors:
- Shi, Yu
- Fu, Zongliang
- Chen, Shuo
- Zhao, Bohan
- Xu, Wei
- Zhang, Changshui
- Li, Jian
citation_count: 9
cited_by: []
cites:
- id: sirignano2018universal
  type: extends
doc_id: shi2025kronos
doi: ''
et_al: false
influential_citation_count: 0
pdf_path: papers/2508.02739.pdf
reading_status:
  global: unread
related: []
resource_type: preprint
s2_id: 5a5302dc0bdd3d40e4ec923d164d84246229874b
tags:
- foundation models
- time series
- finance
- deep learning
- transformers
themes: []
title: "Kronos: A Foundation Model for the Language of Financial Markets"
tldr: Kronos is proposed, a unified, scalable pre-training framework tailored to financial K-line modeling that achieves a 9% lower MAE in volatility forecasting and a 22% improvement in generative fidelity for synthetic K-line sequences and is established as a robust, versatile foundation model for end-to-end financial time series analysis.
url: https://arxiv.org/abs/2508.02739
venue: ''
year: 2025
---
## Notes

(Add your notes here)
