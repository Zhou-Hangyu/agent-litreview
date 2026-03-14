---
abstract: Financial markets are complex systems characterized by high statistical noise, nonlinearity, volatility, and constant evolution. Thus, modeling them is extremely hard. Here, we address the task of generating realistic and responsive Limit Order Book (LOB) market simulations, which are fundamental for calibrating and testing trading strategies, performing market impact experiments, and generating synthetic market data. We propose a novel TRAnsformer-based Denoising Diffusion Probabilistic Engine for LOB Simulations (TRADES). TRADES generates realistic order flows as time series conditioned on the state of the market, leveraging a transformer-based architecture that captures the temporal and spatial characteristics of high-frequency market data. There is a notable absence of quantitative metrics for evaluating generative market simulation models in the literature. To tackle this problem, we adapt the predictive score, a metric measured as an MAE, to market data by training a stock price predictive model on synthetic data and testing it on real data. We compare TRADES with previous works on two stocks, reporting a 3.27 and 3.48 improvement over SoTA according to the predictive score, demonstrating that we generate useful synthetic market data for financial downstream tasks. Furthermore, we assess TRADES's market simulation realism and responsiveness, showing that it effectively learns the conditional data distribution and successfully reacts to an experimental agent, giving sprout to possible calibrations and evaluations of trading strategies and market impact experiments. To perform the experiments, we developed DeepMarket, the first open-source Python framework for LOB market simulation with deep learning. In our repository, we include a synthetic LOB dataset composed of TRADES's generated simulations.
arxiv_id: '2502.07071'
authors:
- Berti, Leonardo
- Prenkaj, Bardh
- Velardi, Paola
citation_count: 5
cited_by:
- id: cao2025financial
  type: uses_method
- id: nagy2025lob
  type: surveys
- id: wang2026difflob
  type: uses_method
cites:
- id: dwarakanath2024abides
  type: extends
doc_id: berti2025trades
doi: 10.3233/FAIA251249
et_al: false
influential_citation_count: 0
pdf_path: papers/2502.07071.pdf
reading_status:
  global: unread
related: []
resource_type: paper
s2_id: f146f816c39d39c0fe1c3016a7702b45fef79768
tags:
- diffusion models
- limit order book
- market simulation
- deep learning
- transformers
themes: []
title: "TRADES: Generating Realistic Market Simulations with Diffusion Models"
tldr: This work proposes a novel TRAnsformer-based Denoising Diffusion Probabilistic Engine for LOB Simulations (TRADES), and assess TRADES's market simulation realism and responsiveness, showing that it effectively learns the conditional data distribution and successfully reacts to an experimental agent, giving sprout to possible calibrations and evaluations of trading strategies and market impact experiments.
url: https://arxiv.org/abs/2502.07071
venue: European Conference on Artificial Intelligence
year: 2025
---
## Notes

(Add your notes here)
