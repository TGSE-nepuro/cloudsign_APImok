# クラウドサインAPI mok プロジェクト

## プロジェクト概要
クラウドサイン（電子契約SaaS）のWeb APIと連携する案件管理アプリケーション。
Django製のスタンドアローンWebアプリ。Sandbox環境のみ接続。

## ディレクトリ構成
```
cloudsign_APImok/
├── cloudsign_project/      # Djangoプロジェクト設定
│   ├── settings.py         # 共通設定
│   ├── settings_local.py.mac  # Mac用ローカル設定テンプレート
│   ├── urls.py             # ルートURL設定
│   ├── templates/          # 共通テンプレート
├── projects/               # メインアプリ
│   ├── models.py           # DB モデル（Project, ContractFile, CloudSignConfig, Participant）
│   ├── views.py            # ビュー
│   ├── forms.py            # フォーム
│   ├── urls.py             # URLルーティング
│   ├── cloudsign_api.py    # CloudSign APIクライアント（シングルトン）
│   ├── tests.py            # テスト
│   └── templates/          # アプリテンプレート
├── media/                  # アップロードファイル（PDF）
├── log/                    # ログファイル
├── venv/                   # Python仮想環境
├── requirements.txt        # 依存パッケージ
├── manage.py               # Django管理コマンド
└── CloudSign-cloudsign-web_api-0.31.0-resolved.yaml  # CloudSign API仕様書
```

## 技術スタック
- 言語: Python 3.x
- フレームワーク: Django 4.2.x
- DB: MySQL（PyMySQLでMySQLdb互換）
- 仮想環境: venv
- API連携: CloudSign Web API（Sandbox環境）

## よく使うコマンド
```bash
# 仮想環境の有効化（Mac）
source venv/bin/activate

# 仮想環境の有効化（Windows）
venv\Scripts\activate

# 開発サーバー起動
python manage.py runserver

# マイグレーション作成・適用
python manage.py makemigrations
python manage.py migrate

# テスト実行
python manage.py test projects

# 依存パッケージインストール
pip install -r requirements.txt
```

## 開発ルール
- **TDD必須**: 実装前にテストを書く。テスト→実装→リファクタの順
- **テストレビュー**: テストコード作成後、フラットな視点でレビュー・修正を実施
- **コメント**: コードには日本語コメントを付与し、処理内容を明確にする
- **Git管理**: コード変更のたびに適切にコミット。最終的にGitHubへPush
- **根本解決**: エラー発生時はその場しのぎではなく根本原因を解決する
- **確認必須**: 作業前は必ず実施可否をユーザーに確認する
- **不明点確認**: 曖昧な点・不明点はその都度確認する

## セッション再開時
- 再起動後にユーザーが出すべき指示は `Claude Codeに出すべき指示.md` を参照

## 作業記録
- 作業を行った都度、`作業記録.txt` に以下の形式で記録する

```
#### YYYY-MM-DD HH:MM　<作業タイトル>
- 実施内容を箇条書きで記載
- 発生した問題と対応内容も記載
```

- 例：
```
#### 2026-02-27 10:00　CloudSign APIトークン取得機能の修正
- `cloudsign_api.py` の `_get_access_token` メソッドのエラーハンドリングを修正
- 401エラー時に自動で再取得するリトライ処理を追加
```

## 主要モデル
| モデル | 用途 |
|---|---|
| `Project` | 案件（タイトル・概要・顧客情報・期日・金額・CloudSign Document ID） |
| `ContractFile` | 案件に紐づくPDFファイル（最大20MB） |
| `CloudSignConfig` | CloudSign APIの接続設定（シングルトン）|
| `Participant` | 書類の宛先情報 |

## CloudSign API
- 接続先: Sandbox環境（`https://api-sandbox.cloudsign.jp`）
- クライアント: `projects/cloudsign_api.py`（シングルトンパターン）
- API仕様書: `CloudSign-cloudsign-web_api-0.31.0-resolved.yaml`
- 主要機能: アクセストークン取得・書類情報取得・書類作成・宛先設定・書類編集

## 追加・変更要件
- `指示書.txt` 作成後に追加・変更された要件はこのセクションに都度追記する
- 元の指示との重複は避け、差分のみを記載する

### 追加要件：組込み署名機能
- API仕様は @CloudSign-cloudsign-web_api-0.31.0-resolved.yaml を参照
- 機能仕様書は以下を参照：
  - @docs/組込み署名（SMS認証）_API資料 .pdf
  - @docs/組込み署名（SMS認証）機能について.pdf

#### 機能要件
1. 送信画面を以下の3種類に分割すること
   - ① 通常の送信（既存機能・メールアドレス入力あり）
   - ② 組込み署名（SMS認証）での送信（メールアドレス入力不要）
   - ③ 簡易認証での送信（メールアドレス入力不要）
2. 同意用マイページ画面を追加すること
3. 案件一覧画面で組込み署名で送信済みであることが確認できること

## エージェントチーム構成（合意済み）
- 意思決定層
  - 総帥（ノストラダムス）: プロダクトオーナーAI（目的定義、MVP決定、優先順位判断、スコープ制御）
  - 副総帥（黒衣の参謀）: テックリード／アーキテクトAI（全体設計、技術選定、非機能設計、アーキテクチャ統制）
- 構想・設計層
  - 情報収集官（レイヴン）: 要件定義AI（業務整理、ステークホルダー整理、ユースケース定義）
  - 予言者（オラクル）: UX設計AI（画面設計、操作フロー設計、仮UI作成）
  - 影の予言者（ミラージュ）: UX検証AI（ユーザー視点レビュー、UI改善提案、認知負荷分析）
- 実装層
  - 実行統括者（デスロード）: 開発オーケストレーターAI（タスク分解、実装順序最適化、依存関係管理）
  - 精密執行者（スカルペル）: バックエンド実装AI（API設計、ビジネスロジック実装、バリデーション）
  - 精密執行者・改（ブレード）: フロントエンド実装AI（UI実装、状態管理、表示ロジック）
  - 数字の番人（アーキビスト）: DB・データ設計AI（ER設計、パフォーマンス設計、データ整合性管理）
- 防衛・改善層
  - 異端審問官（インクイジター）: セキュリティ／異常系設計AI（脆弱性検出、権限設計確認、例外処理設計）
  - 改善の亡霊（リファクター）: 品質向上・CI最適化AI（コードレビュー、テスト自動生成、パフォーマンス改善）
- 最終裁定（独立）
  - 審判者（The Arbiter）: 最終QA／リリース判定AI（結合テスト、仕様逸脱確認、Go/No-Go判断）

## 構成のポイント
- 設計は複数視点
- 実装は並列
- セキュリティは独立
- QAは完全中立
- 複数配置推奨領域: UX／実装／品質レビュー

## 注意事項
- Docker不使用
- 認証認可・ユーザー管理機能は不要
- Windows・Mac両方で動作すること
- 将来的なAWS移行を考慮した構成
- マイクロサービスアーキテクチャを基本とする
- DBは第三正規形が基本
