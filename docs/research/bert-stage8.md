# 階段 8 BERT 調查（bert-stage8，2026-10-21）

**結論**（只列事實與來源；「建議」為調查者意見，決策歸甲方與 architect）
1. 繁中語料有明文的只有 ckiplab/bert-base-chinese，授權 GPL-3.0；其餘 Apache-2.0 的頁面未說明語料是否繁中。GPL 是否及於權重散布：查不到判定，需法務確認。
2. 匯出可用 `optimum-cli export onnx` 或 `torch.onnx.export`；int8 動態量化在論文中 BERT-base GLUE 平均掉 1.7 點（非 ORT 實測），需自測。
3. onnxruntime 1.31.0 有 cp312 x86_64／aarch64 wheel；Colab 單次上限 12 小時；Kaggle 官方額度擷取失敗；BERT-base 512／256 CPU 延遲與記憶體查不到可引用數字。

## 1. 候選中文 BERT
| 模型 | 授權（照抄） | 參數量（照抄） | 繁中／語料 |
|---|---|---|---|
| ckiplab/bert-base-chinese | `License: gpl-3.0`（HF）；repo `GPL-3.0 license` | 文件表 BERT Base `102M` | 明寫繁中；ZhWiki（OpenCC 轉繁）＋ CNA |
| hfl/chinese-roberta-wwm-ext | `License: apache-2.0` | 未列 | 未說明；作者 README 寫「如果要处理繁体中文数据，请使用`BERT`或者`BERT-wwm`」 |
| google-bert/bert-base-chinese | `License: apache-2.0` | 未列 | 未說明 |
| hfl/chinese-macbert-base | `License: apache-2.0` | `0.1B params` | 未說明 |
| Langboat/mengzi-bert-base | `License: apache-2.0` | 未列 | 未說明（`300G Chinese corpus`） |

- 來源：<https://huggingface.co/ckiplab/bert-base-chinese>、<https://github.com/ckiplab/ckip-transformers>、<https://huggingface.co/hfl/chinese-roberta-wwm-ext>、<https://github.com/ymcui/Chinese-BERT-wwm>、<https://huggingface.co/google-bert/bert-base-chinese>、<https://huggingface.co/hfl/chinese-macbert-base>、<https://huggingface.co/Langboat/mengzi-bert-base>；五頁皆無最後更新日期（查不到）。
- 影響：選 ckiplab 則模型散布條件要過法務（決策④，交 manager）；選 Apache-2.0 候選則繁中效果靠甲方測試集驗證。建議 bert-design 把授權與繁中列為選型硬條件。

## 2. ONNX 匯出與 int8 量化
- `optimum-cli export onnx` 有 `--task`、`--opset`、`--dynamo`，動態軸預設開（`--no-dynamic-axes` 才關）。`--dynamo` 原文「recommended option for opset >= 18」，同頁另寫 dynamo=False「is recommended for any ONNX opset = 18」，矛盾，查不到固定建議值。<https://huggingface.co/docs/optimum/exporters/onnx/usage_guides/export_a_model>
- ORT 原文「Quantization is not a loss-less transformation. It may negatively affect a model's accuracy.」，transformer 建議動態量化。<https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html>
- BERT-base-cased GLUE 平均 FP32 `82.0`、I8 `80.3`（約掉 1.7 點）；CoLA `58.0`→`48.3`，MRPC `88.5`→`88.8`，SST-2 `92.3`→`92.1`。<https://ar5iv.labs.arxiv.org/html/2211.09744>（Table 3，標準 8-bit）
- 論壇個案（非官方）：DistilBERT XNLI ONNX 動態量化掉到約 `0.33`（原 `0.78`），建議 `per_channel=False`。<https://discuss.huggingface.co/t/dynamic-quantization-problems/24423>
- 影響：建議 notebook 同時匯出 fp32 與 int8，用同一人工測試集比較；opset 與動態軸在 notebook 內以 PyTorch vs ONNX logits 比對。

## 3. CPU 延遲、記憶體與 wheel
- onnxruntime `1.31.0`（PyPI 上傳 `Oct 9, 2026`）：`onnxruntime-1.31.0-cp312-cp312-manylinux_2_28_x86_64.whl`、`...manylinux_2_28_aarch64.whl`；`Requires-Python: >=3.11`。<https://pypi.org/project/onnxruntime/>
- tokenizers `0.23.3`：`Requires-Python >=3.10`；Linux 列 `cp310-abi3-manylinux_2_17_x86_64` 與 aarch64 wheel，頁面未見 cp312 專屬 wheel（abi3 理論可裝於 3.12，未實測）。<https://pypi.org/project/tokenizers/>
- 延遲：查不到 BERT-base、ORT、CPU、seq 512／256 的可引用數字。搜尋摘要（原頁 403）：BERT Base 動態量化 ONNX、seq 128、8 threads 平均 `18.5ms`。<https://blog.x.com/engineering/en_us/topics/insights/2021/speeding-up-transformer-cpu-inference-in-google-cloud>
- 非 BERT-base（摘要，未開啟）：seq 256 int8 `26 ms` vs fp32 `46 ms`；seq 1024 int8 `382 ms` vs fp32 `202 ms`，提示長序列 int8 不占優。<https://arxiv.org/pdf/2606.04171>
- 記憶體：二手來源「more than 400MB」。<https://getstream.io/blog/optimize-transformer-inference/> 推算（未實測）：`110M` 參數（<https://huggingface.co/google-bert/bert-base-uncased>）× 4 bytes ≈ 440MB。
- 影響：512 與 256 須在實機測；spec 7.27 已允許改 256。wheel 對 macOS Docker（linux aarch64）與 Oracle ARM（glibc ≥ 2.28）足夠，仍需 `uv lock` 驗證。

## 4. Colab／Kaggle 免費方案與條款
- Colab：「notebooks can run for at most 12 hours, depending on availability and your usage patterns.」「Colab does not publish these limits」（GPU 額度）。<https://research.google.com/colaboratory/faq.html>；免費 GPU 每週時數查不到官方數字。
- Kaggle：官方頁擷取只得標題，原文查不到。次要來源（搜尋摘要）：GPU「up to 30 GPU hours per week」、單次「up to 9 hours」，另一來源稱 12 小時，互相衝突。<https://www.kaggle.com/page/GPU-tips-and-tricks>
- 私有資料集：DataCamp「private datasets are visible only to you」；Packt 稱建立時可選 public 或 private。<https://www.datacamp.com/tutorial/tutorial-kaggle-datasets-tutorials-kaggle-notebooks>、<https://www.packtpub.com/en-ee/product/developing-kaggle-notebooks-1-9781805128519/chapter/introducing-kaggle-and-its-basic-functions/kaggle-datasets>；官方原文查不到，建議實機確認預設。
- 條款（摘要，原頁擷取失敗）：「for internal, personal, non-commercial use」。<https://kaggle.com/terms>；爬取論壇內容的明文限制：查不到。Colab 只明列禁止濫用與勿放個人資訊。<https://research.google.com/colaboratory/faq.html>
- 影響：非商用條款與商用前景衝突，需法務確認（決策④）；spec 7.27 限定只上傳無作者與推文帳號的欄位，建議維持。

## Colab 與 Google AI Pro（查詢日 2026-10-21）
**結論**
1. Google AI 方案附 Colab 福利（官方公告 2026-09-22）；官方未列 CU 數，二手來源稱 Pro 每月約 200 CU；台灣是否開放：查不到。
2. 免費版 GPU 種類與額度官方不公開，單次上限 12 小時；Pro／Pay As You Go 依 CU 餘額；GPU 單價以第三方實測為準。
3. 推估：BERT-base 1 萬篇、512、3 epoch 單次約 1–2 CU（約 US$0.1–0.2）；若 AI Pro 的 200 CU 實際可用則不需另付，否則二手報導的最低購買為 US$9.99／100 CU。
- Q1：官方 [Google Developers Blog](https://developers.googleblog.com/colab-is-now-part-of-your-google-ai-plan/)（2026-09-22）：「priority access to faster accelerators and more powerful machines」，僅適用「Google AI subscribers in Colab supported countries」（未列國家）；未列 CU 數、啟用步驟。二手 [aipromonow](https://www.aipromonow.com/en/promos/google-ai-plan-colab-premium-benefits-sep2026)「about 200 Colab Compute Units per month」、[inside.com.tw](https://www.inside.com.tw/article/42497-google-ai-pro-colab-200-compute-units-a100-cli)（2026/09/27）「每月可獲得 200 個 Colab 運算單元」，未經官方證實。[Google AI 方案頁](https://one.google.com/about/google-ai-plans/)無 Colab 字樣，列 150+ 國家、5 TB 儲存。[Colab FAQ](https://research.google.com/colaboratory/faq.html)：免費試用中不含。
- Q2：免費版 12 小時上限、GPU 種類「vary over time」、額度不公開（[FAQ](https://research.google.com/colaboratory/faq.html)）。Pro 100 CU／月、Pro+ 500 CU／月（[Workspace 部落格，2024-06-25](https://workspaceupdates.googleblog.com/2024/06/google-workspace-colab-pro-and-colab-pro-plus.html)，舊資料）。官方定價頁無數字（[signup](https://colab.research.google.com/signup) 只回傳標題，查不到官方價格）；二手 $10／100 CU、無折扣（[McCormick，2026-03 更新，查於 2026-03-10，南加州](https://mccormickml.com/2024/04/23/colab-gpus-features-and-pricing/)）。每小時：T4 1.19、L4 1.71、A100 40GB 5.40、A100 80GB 7.52 CU；該頁註明「fluctuate」，非官方。
- Q3（推估，未實測）：以 6×參數×token 約 1e16 FLOPs（110M × 1 萬篇 × 512 × 3）；假設實效 2–5 TFLOPS 得 T4 約 0.5–1.5 小時 ≈ 0.6–1.8 CU ≈ US$0.06–0.18；含失敗重跑與調參（×10）約 US$1–2。
