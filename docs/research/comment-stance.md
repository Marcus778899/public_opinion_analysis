# PTT 推文立場分類：外部資訊（2026-10-26）

**結論**（只列事實；「建議」為調查者意見，決策歸甲方）
1. 中文立場有 Weibo 對話資料集 C-MTCSD（三類、平均 kappa 0.934）；中文反諷占比與 PTT 推文立場的公開數字查不到。
2. Groq 主要標註模型 `qwen/qwen3.8-27b` 列為 Preview，且不在 Batch 支援清單；Groq 稱 Preview「should not be used in production environments」。
3. BERT-base 短文字 CPU 毫秒數查不到可引用原頁數字，只有相對加速比。

## 1. 立場與反諷資料
- C-MTCSD：Weibo 對話留言 24,264 則，標籤 "Against"、"Favor"、"None"，每則至少兩人標，平均 kappa 0.934、一致性 0.972。<https://arxiv.org/html/2504.09958v2>
- 同論文摘要級：SOTA 模型零樣本 F1 "64.07%"（搜尋摘要，未核原文）。<https://arxiv.org/abs/2504.09958>
- 反諷占比（抽樣結果，不代表整體）：Gong et al. 2020，新聞網站留言，2,486 反諷 vs 89,296 非反諷，由此算約 2.7%。<https://aclanthology.org/2020.lrec-1.619/>
- Ciron（Weibo 8.7K+ 則）標註一致度與反諷比例查不到。<https://aclanthology.org/2020.lrec-1.701/>；「中文社群反諷約 10%」一說無法核實（來源頁摘要未提反諷）<https://arxiv.org/abs/2204.09366>
- CFMS（中文多模態反諷，kappa 0.69，摘要級）。<https://arxiv.org/pdf/2604.16372>

## 2. 推／噓作為輔助特徵
- PTT 推／噓／→ 三種標記，每則上限 27 個中文字（摘要級，PDF 無法解析）。<https://bcmi.sjtu.edu.cn/~paclic29/proceedings/PACLIC29-2004.210.pdf>
- 台大碩論稱語言線索可提升立場分類準確率「up to 20 percent」（搜尋摘要，條件不明）。<https://scholars.lib.ntu.edu.tw/entities/publication/4028f70d-49f4-401e-8634-4cb59a9a85f5>
- Facebook 反應當反諷特徵：摘要只稱 "acceptable performance metrics"，數字查不到。<https://arxiv.org/abs/1805.06510>
- 推噓當立場輔助特徵的直接研究：查不到。本專案 S3-05 驗證推噓作弱標註不採用（設計 15.6）。

## 3. BERT-base 短文字 CPU 延遲
- BERT Base 動態量化 ONNX、seq 128、8 threads 平均 18.5 ms（經 bert-stage8 轉述，原頁未開）。<https://blog.x.com/engineering/en_us/topics/insights/2021/speeding-up-transformer-cpu-inference-in-google-cloud>
- Microsoft Intel CPU：4 threads 下量化 BERT 12 層約 2.9 倍、蒸餾 3.38 倍（相對值，無毫秒）。<https://opensource.microsoft.com/blog/2021/03/01/optimizing-bert-model-for-intel-cpu-cores-using-onnx-runtime-default-execution-provider/>
- int8 加速比：I-BERT 給 seq 128／256，無 seq 32 數字；截短 max_len 的準確度影響查不到。<https://arxiv.org/pdf/2101.01321> 建議：27 字上限下 max_len 取 64 左右，待實機量測。

## 4. Groq 與其他低價 API（每 1M tokens，USD）
- Groq 價格來源 <https://console.groq.com/docs/models>（groq.com/pricing 擷取不到表格）：qwen/qwen3.8-27b $0.80 input / $4.00 output（Preview）；openai/gpt-oss-20b $0.075 / $0.30；openai/gpt-oss-120b $0.15 / $0.60（Production）。
- Batch：「Pricing is at a 50% cost discount compared to synchronous API pricing.」窗口 "24 hours to 7 days"，逾時 expired；支援模型不含 qwen3.8-27b；「does not stack with prompt caching discounts」。<https://console.groq.com/docs/batch>
- Rate limit 表（頁面稱 Developer plan 基準）：qwen3.8-27b 與 gpt-oss-20b 均為 RPM 30、RPD 1K、TPM 8K、TPD 200K；免費層數字查不到。<https://console.groq.com/docs/rate-limits>
- 下架：無固定通知期；preview "may be discontinued at short notice with limited advance warning"；qwen3.6-27b 於 2026-09-14 下架，替換為 qwen3.8-27b。<https://console.groq.com/docs/deprecations>
- Gemini：2.5 Flash-Lite $0.10 / $0.40，Batch $0.05 / $0.20；3.1 Flash-Lite $0.25（text）/ $1.50，Batch $0.125 / $0.75；免費層 "Free of charge"，Batch 免費層 "Not available"。<https://ai.google.dev/gemini-api/docs/pricing>（"Last updated 2026-10-22 UTC"）
- OpenAI：gpt-5-nano $0.05 / $0.40，Batch $0.025 / $0.20；gpt-4.1-nano $0.10 / $0.40，Batch $0.05 / $0.20（列表未全數核實）。<https://developers.openai.com/api/docs/pricing>
- DeepSeek deepseek-flash：cache miss $0.15（off-peak）/ $0.3（peak），output $0.6 / $1.2；peak 為 UTC 01–04、06–10 週一至五。<https://api-docs.deepseek.com/quick_start/pricing>

## 5. 送外部 LLM 前的去識別
- 去除帳號等可直接識別資料；以金鑰 HMAC-SHA256 做一致假名，金鑰外洩即可反推（摘要級）。<https://www.red-gate.com/simple-talk/data-security-privacy-compliance/how-to-anonymize-pii-in-llm-pipelines-5-key-techniques-explained/>
- Presidio 內建 PII recognizers，但 supported entities 頁未列中文（zh）預設 recognizer，中文效果查不到。<https://presidio.dataprivacystack.org/supported_entities/>
- 個資法施行細則第17條（代碼、匿名、隱藏部分資料）為二手引述，現行條文未核實；去識別後是否仍屬個資需法務判斷（決策④）。<https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=I0050021>
