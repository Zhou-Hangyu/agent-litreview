---
abstract: Foundation models have transformed domains from language to genomics by learning general-purpose representations from large-scale, heterogeneous data. We introduce TradeFM, a 524M-parameter generative Transformer that brings this paradigm to market microstructure, learning directly from billions of trade events across>9K equities. To enable cross-asset generalization, we develop scale-invariant features and a universal tokenization scheme that map the heterogeneous, multi-modal event stream of order flow into a unified discrete sequence -- eliminating asset-specific calibration. Integrated with a deterministic market simulator, TradeFM-generated rollouts reproduce key stylized facts of financial returns, including heavy tails, volatility clustering, and absence of return autocorrelation. Quantitatively, TradeFM achieves 2-3x lower distributional error than Compound Hawkes baselines and generalizes zero-shot to geographically out-of-distribution APAC markets with moderate perplexity degradation. Together, these results suggest that scale-invariant trade representations capture transferable structure in market microstructure, opening a path toward synthetic data generation, stress testing, and learning-based trading agents.
arxiv_id: '2602.23784'
authors:
- Kawawa-Beaudan, Maxime
- Sood, Srijan
- Papasotiriou, Kassiani
- Borrajo, Daniel
- Veloso, Manuela
citation_count: 0
cited_by:
- id: cao2025from
  type: surveys
- id: nagy2025lob
  type: surveys
cites:
- id: sirignano2018universal
  type: extends
- id: li2024mars
  type: extends
doc_id: kawawa-beaudan2026tradefm
doi: ''
et_al: false
influential_citation_count: 0
pdf_path: papers/2602.23784.pdf
reading_status:
  global: unread
related: []
resource_type: preprint
s2_id: 0712ecdd042d258ef049ce838494b04d9c4728cd
tags:
- foundation models
- market microstructure
- transformers
- deep learning
- trading
themes: []
title: "TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure"
tldr: TradeFM is introduced, a 524M-parameter generative Transformer that brings this paradigm to market microstructure, learning directly from billions of trade events across>9K equities, and suggests that scale-invariant trade representations capture transferable structure in market microstructure.
url: https://arxiv.org/abs/2602.23784
venue: ''
year: 2026
---
## Notes

(Add your notes here)
