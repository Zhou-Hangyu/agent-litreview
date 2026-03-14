---
abstract: "Modern generative models for limit order books (LOBs) can reproduce realistic market dynamics, but remain fundamentally passive: they either model what typically happens without accounting for hypothetical future market conditions, or they require interaction with another agent to explore alternative outcomes. This limits their usefulness for stress testing, scenario analysis, and decision-making. We propose \\textbf{DiffLOB}, a regime-conditioned \\textbf{Diff}usion model for controllable and counterfactual generation of \\textbf{LOB} trajectories. DiffLOB explicitly conditions the generative process on future market regimes--including trend, volatility, liquidity, and order-flow imbalance, which enables the model to answer counterfactual queries of the form: ``If the future market regime were X instead of Y, how would the limit order book evolve?''Our systematic evaluation framework for counterfactual LOB generation consists of three criteria: (1) \\textit{Controllable Realism}, measuring how well generated trajectories can reproduce marginal distributions, temporal dependence structure and regime variables; (2) \\textit{Counterfactual validity}, testing whether interventions on future regimes induce consistent changes in the generated LOB dynamics; (3) \\textit{Counterfactual usefulness}, assessing whether synthetic counterfactual trajectories improve downstream prediction of future market regimes."
arxiv_id: '2602.03776'
authors:
- Wang, Zhuohan
- Ventre, Carmine
citation_count: 0
cited_by: []
cites:
- id: berti2025trades
  type: uses_method
doc_id: wang2026difflob
doi: ''
et_al: false
influential_citation_count: 0
pdf_path: papers/2602.03776.pdf
reading_status:
  global: unread
related: []
resource_type: preprint
s2_id: 59289ec36a716b54985d12e08031fb709b352386
tags:
- diffusion models
- limit order book
- deep learning
- market simulation
themes: []
title: "DiffLOB: Diffusion Models for Counterfactual Generation in Limit Order Books"
tldr: "DiffLOB explicitly conditions the generative process on future market regimes--including trend, volatility, liquidity, and order-flow imbalance, which enables the model to answer counterfactual queries of the form: ``If the future market regime were X instead of Y, how would the limit order book evolve?''"
url: https://arxiv.org/abs/2602.03776
venue: ''
year: 2026
---
## Notes

(Add your notes here)
