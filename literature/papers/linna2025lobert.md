---
abstract: Modeling the dynamics of financial Limit Order Books (LOB) at the message level is challenging due to irregular event timing, rapid regime shifts, and the reactions of high-frequency traders to visible order flow. Previous LOB models require cumbersome data representations and lack adaptability outside their original tasks, leading us to introduce LOBERT, a general-purpose encoder-only foundation model for LOB data suitable for downstream fine-tuning. LOBERT adapts the original BERT architecture for LOB data by using a novel tokenization scheme that treats complete multi-dimensional messages as single tokens while retaining continuous representations of price, volume, and time. With these methods, LOBERT achieves leading performance in tasks such as predicting mid-price movements and next messages, while reducing the required context length compared to previous methods.
arxiv_id: '2511.12563'
authors:
- Linna, Eljas
- Baltakys, K.
- Iosifidis, A.
- Kanniainen, J.
citation_count: 0
cited_by: []
cites:
- id: gould2013limit
  type: uses_method
doc_id: linna2025lobert
doi: 10.48550/arXiv.2511.12563
et_al: false
influential_citation_count: 0
pdf_path: papers/2511.12563.pdf
reading_status:
  global: unread
related: []
resource_type: preprint
s2_id: 36a5e3b9de5acbbd982caccea4fa0f68d777c52d
tags:
- limit order book
- transformers
- foundation models
- deep learning
themes: []
title: "LOBERT: Generative AI Foundation Model for Limit Order Book Messages"
tldr: This work introduces LOBERT, a general-purpose encoder-only foundation model for LOB data suitable for downstream fine-tuning and achieves leading performance in tasks such as predicting mid-price movements and next messages, while reducing the required context length compared to previous methods.
url: https://arxiv.org/abs/2511.12563
venue: arXiv.org
year: 2025
---
## Notes

(Add your notes here)
