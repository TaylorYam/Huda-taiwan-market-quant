# Data Contract v0.1

- 狀態：Draft；欄位語義可供收集器實作，現貨因子來源及實體儲存方案仍待決。
- 日期：2026-09-15

本契約定義官方市場資料進入系統後的共同時間、來源、單位、維護方式及缺值語義。它定義邏輯資料形狀，不指定 JSON、Parquet、SQLite 或其他實體儲存技術；持久化選擇須依 ADR 流程決定。

## 設計原則

1. 原始觀察值與正規化欄位分開保存；正規化不可抹去來源欄位、來源單位或契約／盤別維度。
2. 不同單位或模型口徑使用不同 `dataset_id`，禁止把股數轉填成金額，也禁止無版本地混合。
3. 來源修訂採追加版本並保留前版；不可覆寫已被因子或回測引用的原始觀察值。
4. 每筆資料可追到官方來源、交易日、發布／版本時間、擷取時間和解析版本。
5. 缺值與抓取錯誤有明確狀態；不可填成 0、中性分數或前值，除非來源明確提供該值且規格允許。
6. 原始下載檔、資料庫、憑證及執行期狀態不提交 Git。遵守來源的授權、訂閱與再散布條款。

## 時間語義

所有時間戳須包含時區，資料處理與交易日期以 `Asia/Taipei` 為準；系統事件 `retrieved_at` 使用 UTC。

| 欄位 | 語義 |
|---|---|
| `observation_date` | 官方觀察所屬的交易日／指數日期，正規化為 `YYYY-MM-DD`。期貨夜盤一律沿用 TAIFEX 官方交易日期，不自行用曆日重算。 |
| `source_date` | 官方回應、報表或檔案中原樣提供的日期；若等於 `observation_date` 仍保留，方便稽核映射。 |
| `published_at` | 官方版本可用時間，含時區；來源未提供時為 null，另保留 `publication_label`（例如報表版本或盤別），不得猜測時間。 |
| `retrieved_at` | 本系統成功取得該版本的時間，UTC RFC 3339。重試可有多個擷取紀錄，但不因此複製觀察值。 |
| `ingested_at` | 該筆觀察進入正規化資料層的時間，UTC RFC 3339。 |
| `effective_at` | 只有來源提供盤中時間戳時使用；保留原始偏移，不代替交易日。 |

回測的 `as_of` 判斷使用當時實際可取得的版本（`published_at`；缺少時採該資料集明確記錄的保守可用時間政策），不能只按 `observation_date` 假設收盤即可得知最終資料。

## 觀察值共同信封

每一個原始或正規化觀察值須能表達以下欄位。若特定來源沒有欄位，保留 null 並附理由，不自行生成虛構值。

| 欄位 | 必填 | 說明 |
|---|---:|---|
| `dataset_id` | 是 | 版本化資料系列名稱，見下表。不同單位必須分開。 |
| `schema_version` | 是 | 契約版本，例如 `0.1`。 |
| `observation_date` | 是 | 正規化交易日。 |
| `source_date` | 是 | 官方原始日期或其可稽核映射。 |
| `source_name` | 是 | `TWSE` 或 `TAIFEX`。 |
| `source_url` | 是 | 官方頁面、API 或商品頁；請求參數可另存，但不得含秘密。 |
| `source_record_key` | 是 | 原始列唯一鍵；包含該資料集需要的商品／投資人／盤別維度。 |
| `published_at` | 否 | 官方公布時間；來源未提供時為 null。 |
| `publication_label` | 否 | 來源版次、盤別或報表類型。 |
| `retrieved_at` | 是 | UTC 擷取時間。 |
| `ingested_at` | 是 | UTC 正規化時間。 |
| `source_revision` | 否 | 官方更正版次／檔案時間；來源無版次時為 null。 |
| `supersedes_id` | 否 | 新版取代舊版時指向舊觀察值。 |
| `source_payload_hash` | 是 | 來源回應或檔案位元組的 SHA-256，用於辨識相同輸入；受授權限制時只保留雜湊及必要欄位。 |
| `parser_version` | 是 | 解析器版本或 Git commit。 |
| `values` | 是 | 來源原值或正規化值；每個數值欄位須有明確單位。 |
| `quality_status` | 是 | `available` 或下方列出的不可用狀態。 |
| `quality_notes` | 否 | 驗證警告、排除原因或欄位映射說明。 |

共同信封只是邏輯契約，不要求所有來源強行塞進一張寬表。TAIFEX 的不同契約、投資人類別、盤別及發布版本須保留成不同 `source_record_key`／維度。

## v0.1 原始資料系列

| `dataset_id` | 核心欄位與單位 | 必須保留的維度／限制 |
|---|---|---|
| `twse_taiex_daily_v1` | `open`, `high`, `low`, `close`；指數點 | `observation_date`；由此計算 MA20、MA60、20 日動能。 |
| `twse_t86_foreign_flow_shares_v1` | 外資及陸資買進、賣出、買賣超股數；股 | 證券代碼、證券名稱、投資人類別、買／賣／淨欄位。此資料不符合目前模型的金額單位，不能輸入金額因子。 |
| `twse_bfi82u_foreign_amount_web_v1` | BFI82U 外資類別買進、賣出、買賣差額；新台幣元 | 免費官方日報表，官方頁標示自 2004-04-07 起並提供 CSV；保留原始外資類別文字及來源日期。早期分類與目前「外資及陸資（不含外資自營商）」／「外資自營商」分列方式是否一致尚未確定。 |
| `twse_bfi82u_foreign_amount_eshop_v1` | BFI82U／BFIBGU 買進、賣出、買賣超金額；新台幣元 | E-Shop 歷史產品另標示自 2004-02-19 起，付費、每筆最多 5 年；來源說明每日 14:50 與 19:40 產製兩個涵蓋範圍不同的版本。不得在確認欄位、分類及版本等價前與公開日報表拼成一條無差別序列。 |
| `twse_fmtqik_market_turnover_twd_v1` | `成交金額`；新台幣元 | TWSE FMTQIK 每日市場成交資訊，官方頁標示自 1990-01-04 起並提供 CSV；含一般、零股、盤後定價、鉅額，排除拍賣與標購。範圍為 TWSE 上市市場，不等於 OTC／期貨成交額。與外資日報表正式對接前仍須做同日數值及交易類型核對。 |
| `taifex_tx_daily_contract_v1` | 開高低收、結算價、成交量、未平倉量；依來源規格記錄點／口 | 商品代碼、到期月份、交易時段／盤別、來源報表版本。不得先合併近月或抹去盤別。 |
| `taifex_futures_investor_oi_v1` | 買／賣／淨交易量及買／賣／淨未平倉量；口 | 商品契約、法人類別、交易日、公布版本／時間。因子使用的 TX 外資及陸資列必須可明確篩選。 |
| `taifex_txo_oi_pcr_v1` | `put_oi`, `call_oi`；口；可衍生 `oi_pcr = put_oi / call_oi`；無單位比值 | 報表來源、TXO 月／週契約合併口徑及交易日。保留分子分母；`call_oi=0` 時 PCR 不可用，不得補值。 |
| `taifex_taiwan_vix_close_v1` | 每日官方收盤 VIX；指數點 | 明確選取收盤欄，區分盤中揭示版本；不可把即時值替代收盤值。 |

`twse_t86_foreign_flow_shares_v1` 不可代替金額序列。TWSE 免費 BFI82U 公開日報表提供金額欄位，是 v0.1 的優先候選來源；在確認可重現歷史查詢、外資類別跨期一致性、公布版本及分母交易範圍前，不把公開表與付費 E-Shop 檔合併，也不宣稱 2004 起整段序列已可直接回測。

## 品質與缺值狀態

`quality_status` 採下列封閉值；可增加狀態須更新契約版本。

| 狀態 | 意義 | 是否可計算核心因子 |
|---|---|---:|
| `available` | 回應成功、必要欄位存在且通過基本型別／範圍驗證 | 是，另受模型規格限制 |
| `not_published` | 尚未到來源公布時間／當日資料尚未發布 | 否 |
| `source_empty` | 官方成功回應但指定日期無觀察值；需區分非交易日與意外空洞 | 否 |
| `fetch_failed` | 網路、HTTP 或來源服務失敗 | 否 |
| `parse_failed` | 回應結構改版或解析失敗 | 否 |
| `invalid` | 必要欄位缺失、型別錯誤、單位／日期／範圍驗證失敗 | 否 |
| `not_applicable` | 來源規則明確表示該日／維度不適用 | 否 |

空值保持 null 並帶 `quality_status`／`quality_notes`；數值 0 只代表來源明確提供零值。資料品質摘要需另外計算預期交易日覆蓋率、重複觀察值、修訂數及各不可用狀態數量。

## 唯一鍵、重跑與修訂

- 邏輯識別鍵：`dataset_id + observation_date + source_record_key + publication_label/source_revision`。
- 同一來源輸入重跑時，以相同 `source_payload_hash` 辨識重複內容，更新擷取紀錄但不複製觀察值。
- 新來源版本或修訂若內容不同，追加新觀察版本並設定 `supersedes_id`；回測可依當時 `published_at` 重建舊版本。
- 來源更正的發現時間、舊值、新值及 parser/schema 版本都要可追溯；不得靜默回寫歷史分數。
- 因子結果另存 `model_version`、`factor_id`、`as_of_date`、使用的輸入觀察版本 ID、輸入窗口起訖、公式版本、分數及可用狀態。Market Score 另存所用因子結果 ID 與權重版本。

## 尚待另行決議

1. 驗證免費 BFI82U 的歷史查詢、早期分類和最終報表版本，並將 FMTQIK 成交金額分母依同一交易日及交易類型核對；只有缺口確實影響目標窗口時才評估 E-Shop 歷史商品。T86 股數仍須作獨立系列，不能替代金額因子。
2. 各來源實際發布時間與要使用的最終報表版次，需以官方說明及可重現實測填入資料集設定。
3. PCR 的歷史回補下界與下載方式、TX 年度 ZIP 最早可選年份、舊 TAIFEX 部位申請結果及官方成交金額分母候選見 [Phase 0 Source Research](phase0-source-research-v0.1.md)；可選年份不等同已驗證 ZIP 內容。
4. 資料庫／檔案格式、保留期、排程執行環境與 GitHub Actions 輸出保存方式須另提 ADR；本契約不預選技術，也不批准購買資料。

## 相關文件

- [Data Availability Probe v0.1](data-availability-probe-v0.1.md)
- [Data Window Policy v0.1](data-window-policy-v0.1.md)
- [Backtest Spec v0.1](backtest-spec-v0.1.md)
- [Development Roadmap v0.1](roadmap-v0.1.md)
