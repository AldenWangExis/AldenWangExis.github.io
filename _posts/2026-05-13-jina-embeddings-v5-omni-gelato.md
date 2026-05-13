---
title: 只训了 0.35% 的权重，Jina 全模态嵌入凭什么用 1.5B 追平 8.9B？
description: Jina AI 发布 jina-embeddings-v5-omni，GELATO 方法冻结主干只训 projector，nano/small 两档以极低参数量追平同类 8B 模型，文本路径零迁移，配合 Milvus 一行不改直接上跨模态 RAG。
author: Alden
date: 2026-05-13 22:00:00 +0800
categories: [LLM Engineering]
tags: [Embedding, RAG, Milvus, Vector Database, LLM, Architecture, Performance, Production]
pin: false
comments: true
---

![](https://jina.ai/blog-banner/jina-embeddings-v5-omni-multimodal-embeddings-for-text-image-audio-and-video.gif)

Jina AI 刚刚发布了 jina-embeddings-v5-omni，分 nano（0.95B）和 small（1.57B）两档，官方叫它全模态向量小模型。一个模型把文本、图像、音频、视频都收进同一条向量里，文本侧与 v5-text 逐字节一致，已有索引一行不用改。

背后的方法叫 GELATO：把预训练好的视觉、音频编码器和文本嵌入模型一起冻结，中间只训一层 projector 把模态特征拉进文本几何里。nano 和 small 这两档接的是完全不同的文本骨干和不同架构，能同时跑通，说明这套方子不止能延长 v5-text——理论上谁的文本嵌入模型都能照此加上视觉和音频。

![Architecture of jina-embeddings-v5-omni](https://cms.jina.ai/content/images/size/w1000/2026/05/architecture.png)

- v5-omni-small 在四模态平均分上拿到 53.93，参数量只有 LCO-Omni-7B（8.93B）的 1/5.7，分数差 0.50 分。
- v5-omni-nano 0.95B，文档检索 ViDoRe 拿到 70.05，同量级的 LanguageBind（1.14B）只有 37.33；nano 的全模态平均分比它高出 8.9 分。
- 全模型只有 0.35% 的权重参与训练。vision 链路训练加速 1.82×，audio 链路 3.22×–3.95×。
- 文本路径与 jina-embeddings-v5-text 行为完全等价，存量索引不用重建。

![](https://arxiv.org/html/2605.08384v2/x1.png)

放到坐标系里，这是当前开源 omni 向量模型的帕累托前沿。

## 01 它好在哪

参数效率这块，把官方对比图按参数量从小到大捋一遍很直观：nano 0.95B 拿 45.19，LanguageBind 1.14B 拿 36.27，small 1.57B 一下蹦到 53.93。再往上看，4.70B 的 Omni-Embed-Nemotron 反而只有 41.21，同样 4.70B 的 LCO-Omni-3B 是 53.83，8.93B 的 LCO-Omni-7B 也才 54.43。换句话说 small 在 2B 以下没有同档对手，要打平它得花 5 倍以上的参数。官方的措辞挺克制，叫"两亿参数以下最强的开源全模态嵌入"，没去抢"最强多模态"这个招牌，1/5.7 参数追平这个事实本身已经够硬了。

文本路径无损这件事，对在跑生产的人是真有用。Jina 给的承诺用的是 "exactly the same" 和 "identical" 这种强词，意思就是你今天用 v5-text 建好的索引，明天换 v5-omni 推理纯文本，向量在数学上一模一样，ANN 不用重建，阈值不用重新调。文本评测分 MMTEB 67.00 直接沿用 v5-text 的发布数字，在所有 omni 模型里也是最高的。光这一条，对很多已经在跑 v5-text 的团队就足够构成升级理由。

0.35% 的可训练比例是什么意思？训了三块东西：视觉投影的第二层 `fc_vision_2`、音频投影层 `fc_audio`，再加几个模态分隔符 token 的嵌入，统共就这些。文本 transformer 主体、从 Qwen3.5 抽出来的 ViT、从 Qwen2.5-Omni 抽出来的 audio encoder，全部冻结不动。官方跑了一组对照（4 张 H100、bf16、bs=256、15k 步），数字长这样：

| 链路 | 只训 Projector | 端到端 Full | 加速 | 显存节省 |
|---|---|---|---|---|
| small Vision | 0.413 s/step | 0.752 s/step | 1.82× | 42.0% |
| small Audio | 0.617 s/step | 1.989 s/step | 3.22× | 69.0% |
| nano Vision | 0.181 s/step | 0.329 s/step | 1.82× | 30.7% |
| nano Audio | 0.447 s/step | 1.764 s/step | 3.95× | 64.1% |

模态拼接的做法挺直接。图像是 `<|vision_start|>` + N 个 `<|image_pad|>` + `<|vision_end|>`，音频是 `<|audio_start|>` + K 个 `<|audio_pad|>` + `<|audio_end|>`，视频按帧拼成 vision 段串，带声轨的视频就把音频段放在视频段前面。非文本 token 的位置由编码器投影特征覆写，整条序列过同一个文本 transformer，最后 last-token pooling + L2 归一出向量。一次 forward 出结果，没有 ensemble，不用多模型分发。

维度上是 Matryoshka。small 在训练时直接把 `{32, 64, 128, 256, 512, 768, 1024}` 这一串前缀全部当成训练目标，nano 是 `{32, 64, 128, 256, 512, 768}`。官方给的截断曲线：文本和图像截到 32 维只掉 0.18–0.21 nDCG@10，音频截到 256 维基本无损。存储紧张的时候把 768 维砍成 256 维，几乎不掉分，也不用重训。

最亮眼的单项是文档检索。ViDoRe-in-MIEB 是 10 个真实文档检索任务的平均，small 用 0.92B 的文图路径参数拿到 79.08，比 4.07B 的 LCO-Omni-3B（78.24）还高，逼近 8.93B 的 LCO-Omni-7B（80.32）；nano 用 0.31B 的文图路径参数拿到 70.05，把同量级 LanguageBind（0.43B / 37.33）拉开了将近一倍。这条 benchmark 测的就是带扫描件、表格、复杂排版的真实文档，恰好对应企业知识库 RAG 这一类生产场景。

---

## 02 全模态小模型，不等于多向量列替代品

举个例子。一个电商商品页，有标题、有详情图、有评测视频、有商家语音介绍。能不能把它压成一个 768 维向量？技术上可以，v5-omni 就是为这件事准备的，"同一个实体的多模态形态都聚到向量空间相近的位置"恰恰是它最擅长的事。

但同一个商品页还有另一类需求：用户想按"红色、皮质、3000 元以下、好评率 90% 以上"过滤。这是把同一个实体拆成不同维度，每个维度建一列向量或者一列 scalar 字段，再做组合排序。和"把多模态聚到一起"方向是反的，前者是聚合，后者是分列。

把这两件事混在一起，是这两年向量检索领域很常见的一种认知误区。看到"全模态小模型"几个字，有人第一反应是多向量列、稀疏稠密混检、scalar filter 这些工程能力是不是可以一并不用了。恰恰是这个判断需要小心。v5-omni 解决的是"用一条向量打通跨模态语义"，Milvus 多向量列解决的是"用多条向量切分同一实体的不同语义维度"，两件事互补。

官方对边界也讲得挺坦诚。把 small 拆到具体任务粒度看，强弱不是一条平直的线：

- 强项：图像分类（MIEB 全集 68.55，超过 LCO-Omni-3B 的 64.30），图像聚类（84.57 vs 83.24），音频分类（55.89，超过 LCO-Omni-7B 的 53.39），加上前面说的文档检索。
- 持平：图像、音频检索面对 4B–9B 量级基线，差距控制在 3 分以内。
- 弱项：通用图像检索 MIEB Retrieval 38.53（LCO-Omni-3B 是 46.29），视频任务整体落后于 Qwen3-VL-Embedding-8B 这种 8B 量级专用模型，音频聚类 MAEB Clustering 5.99 被 0.15B 的 clap-htsat-fused（22.74）压住。官方在论文里也直接写了"视频任务的表现明显落后于 baseline"。

---

## 03 选型怎么挑

优先选 v5-omni 的场景：

- 企业知识库 RAG，尤其是带扫描件、表格、图表的文档。ViDoRe 上 small 79.08、nano 70.05，是 2B 以下的天花板。
- 已经在用 v5-text，想顺手把图像、音频、视频接进来。文本路径完全等价，平滑升级。
- 跨语言图像和音频检索。在非英语 image-language 和 audio retrieval 上，相对基线均值偏正。
- 图像分类与聚类。低成本做素材库、商品库的初筛和分组。
- 训练成本敏感的内部微调。0.35% 可训练参数，单卡 H100 一晚上跑完。
- 端侧、边缘、低延迟服务，或者维度压缩需求强的高并发场景。配合 Matryoshka 截到 256 维，存储减半，分数基本不掉。

要搭配专用模型的场景：

- 强视频理解（动作识别、长视频时序问答）。Qwen3-VL-Embedding-8B 在 MMEB-Video 上目前最强。（可以参考 [从BGE到 CLIP，从文本到多模态，Embedding 模型选型终极指南](https://mp.weixin.qq.com/s/djcFlLaBfxyOMao_n_epPQ)）
- 通用图像检索极致召回。核心 KPI 是 MIEB Retrieval 这一类的话，LCO-Omni-3B 多 7.76 分。
- 音频聚类专用。clap-htsat-fused 0.15B 在 MAEB Clustering 上的 22.74，到现在还压着各种更大的通用模型。

要保留多向量列的场景：

- 多属性结构化检索（电商、CRM、用户画像）。一个 omni 向量配上几个属性向量再加 scalar filter，比单纯一列向量灵活。
- 同一实体强调"分维度排序加权"的业务。一篇文档既要按主题相关性排，又要按作者权威性排，得两条向量列分别建索引才能玩。

---

## 04 快速在 Milvus 中使用 Jina Embedding

下面这段代码可以直接复制下来跑通。用 v5-omni-nano 把一组文本和图像统一编码进同一个 Milvus collection，然后用文本 query 跨模态召回。环境只要 `pymilvus`、`requests`、一个 [Zilliz Cloud serverless 实例](https://milvus.io/docs/install-overview.md)，以及一个 [Jina API key](https://jina.ai/api-dashboard/embedding)。

```python

import json
import logging
import os

import requests
from pymilvus import DataType, MilvusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("milvus_jina_omni_demo")

# ── Config ──────────────────────────────────────────────────────────────
JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_API_KEY = os.environ["JINA_API_KEY"]
JINA_MODEL = "jina-embeddings-v5-omni-nano"
EMBED_DIM = 768

ZILLIZ_URI = os.environ["ZILLIZ_URI"]
ZILLIZ_TOKEN = os.environ["ZILLIZ_TOKEN"]
COLLECTION_NAME = "jina_omni_nano_demo"


# ── Helper: Jina v5-omni-nano embedding ─────────────────────────────────
_JINA_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {JINA_API_KEY}",
}


def jina_embed(inputs: list[dict[str, str]], task: str) -> list[list[float]]:
    """Embed text/image/audio/video; one input -> one 768-d vector."""
    payload = {
        "model": JINA_MODEL,
        "task": task,
        "normalized": True,
        "input": inputs,
    }
    resp = requests.post(JINA_API_URL, headers=_JINA_HEADERS, data=json.dumps(payload), timeout=60)
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in data]


def jina_embed_pdf(pdf_url: str, task: str) -> list[list[float]]:
    """Embed a single PDF URL; one PDF in -> N server-chunked vectors out."""
    payload = {
        "model": JINA_MODEL,
        "task": task,
        "normalized": True,
        "input": {"pdf": pdf_url},
    }
    resp = requests.post(JINA_API_URL, headers=_JINA_HEADERS, data=json.dumps(payload), timeout=120)
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


# ── 1. Create collection ────────────────────────────────────────────────
def build_collection(client: MilvusClient) -> None:
    """Create a unified cross-modal collection; drop if exists."""
    if client.has_collection(COLLECTION_NAME):
        client.drop_collection(COLLECTION_NAME)
        logger.info("dropped existing collection %s", COLLECTION_NAME)

    schema = client.create_schema()
    schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field("content", DataType.VARCHAR, max_length=2000)
    schema.add_field("modality", DataType.VARCHAR, max_length=20)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=EMBED_DIM)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )

    client.create_collection(
        COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
        consistency_level="Strong",
    )
    logger.info("created collection %s (dim=%d, metric=COSINE)", COLLECTION_NAME, EMBED_DIM)


# ── 2. Demo corpus: regular modalities + PDFs separately ───────────────
CORPUS: dict[str, list[dict[str, str]]] = {
    "text": [
        {"text": "A beautiful sunset over the beach"},
        {"text": "Un beau coucher de soleil sur la plage"},
        {"text": "海滩上美丽的日落"},
        {"text": "浜辺に沈む美しい夕日"},
    ],
    "image": [
        {"image": "https://i.ibb.co/nQNGqL0/beach1.jpg"},
        {"image": "https://i.ibb.co/r5w8hG8/beach2.jpg"},
        {
            "image": (
                "iVBORw0KGgoAAAANSUhEUgAAABwAAAA4CAIAAABhUg/jAAAAMklEQVR4nO3MQREAMAg"
                "AoLkoFreTiSzhy4MARGe9bX99lEqlUqlUKpVKpVKpVCqVHksHaBwCA2cPf0cAAAAA"
                "SUVORK5CYII="
            )
        },
    ],
    "audio": [
        {"audio": "https://storage.googleapis.com/jina-public/example-audio-clip.wav"},
    ],
    "video": [
        {"video": "https://storage.googleapis.com/jina-public/example-video-clip.mp4"},
    ],
}

PDF_DOCUMENTS: list[str] = [
    "https://arxiv.org/pdf/2506.18902",
]


def _readable_content(payload: dict[str, str]) -> str:
    """Display-friendly content; truncate base64 blobs, keep URLs/texts as-is."""
    key, value = next(iter(payload.items()))
    if key == "text" or value.startswith("http"):
        return value
    return f"base64:{value[:40]}..."


# ── 3. Insert: one path per API contract, all into the same 768-d field ─
def insert_corpus(client: MilvusClient) -> None:
    """Embed every modality as retrieval.passage into the shared space."""
    for modality, items in CORPUS.items():
        vectors = jina_embed(items, task="retrieval.passage")
        rows = [
            {"content": _readable_content(item), "modality": modality, "vector": v}
            for item, v in zip(items, vectors, strict=True)
        ]
        client.insert(COLLECTION_NAME, rows)
        logger.info("inserted %d %s items", len(rows), modality)

    for pdf_url in PDF_DOCUMENTS:
        chunks = jina_embed_pdf(pdf_url, task="retrieval.passage")
        rows = [
            {"content": f"{pdf_url}#chunk{i}", "modality": "pdf", "vector": v}
            for i, v in enumerate(chunks)
        ]
        client.insert(COLLECTION_NAME, rows)
        logger.info("inserted %d pdf chunks for %s", len(rows), pdf_url)

    client.flush(COLLECTION_NAME)


# ── 4. Cross-modal search: text query -> text + image hits ──────────────
def cross_modal_search(client: MilvusClient, query_text: str, limit: int = 5) -> None:
    """Search top-k across the unified text+image space with a text query."""
    query_vec = jina_embed([{"text": query_text}], task="retrieval.query")[0]
    results = client.search(
        COLLECTION_NAME,
        data=[query_vec],
        limit=limit,
        output_fields=["content", "modality"],
        search_params={"metric_type": "COSINE"},
    )
    logger.info("Query: %s", query_text)
    for hits in results:
        for rank, hit in enumerate(hits, 1):
            ent = hit["entity"]
            logger.info(
                "  [%d] score=%.4f modality=%s content=%s",
                rank,
                hit["distance"],
                ent["modality"],
                ent["content"][:80],
            )


def main() -> None:
    client = MilvusClient(uri=ZILLIZ_URI, token=ZILLIZ_TOKEN)
    build_collection(client)
    insert_corpus(client)
    cross_modal_search(client, "sunset on the beach")


if __name__ == "__main__":
    main()

```

跨语言的英、中、法三条文本和两张沙滩日落图都进了召回。同一个 768 维向量字段、同一个 COSINE 索引、一次搜索，跨模态跨语言一起回来。注意一下文本和图像的分数档差：文本之间在 0.72–0.77，图像在 0.6 左右，这是 nano 这种小模型在跨模态语义距离上的典型表现，做粗排够用，做精排时建议在业务侧给模态加权或者做二次重排。

几个工程细节顺手提一下：

- task 参数要分场景。入库用 `retrieval.passage`、查询用 `retrieval.query`，每个任务对应一套 LoRA 适配器，混用会掉分。
- `normalized=True` 默认打开，Jina 返回的是 L2 归一向量，所以 Milvus 这边 COSINE 和 IP 数学等价。AUTOINDEX 在 serverless 上会自动选 HNSW 或 IVF。
- dim=768 是 nano 的全维。换 small 就是 1024，建表时改一下。也可以配合 Matryoshka 截到 768 或 512，存储减半，性能几乎不掉。
- 存量索引复用要注意。已经用 v5-text 建好的文本 collection，dim、归一、任务名一致就可以直接把推理端点切到 v5-omni-nano 的 text-only 模式继续用。官方给的是数学上 identical 的承诺，工程上建议先 A/B 一轮再上量。

---

## 资源

- HuggingFace：https://huggingface.co/collections/jinaai/jina-embeddings-v5-omni
- ModelScope 魔搭：https://modelscope.cn/organization/jinaai
- 技术报告：https://jina.ai/news/jina-embeddings-v5-omni-multimodal-embeddings-for-text-image-audio-and-video/
- 论文地址：https://arxiv.org/abs/2605.08384
- Jina API：https://jina.ai/embeddings
- Zilliz Cloud serverless 实例： https://milvus.io/docs/install-overview.md

开源生态里真把"四模态都能用、参数小、文本零迁移、训练只动 0.35% 权重"这几件事同时做到的，jina-embeddings-v5-omni 是第一个。卡在多模态检索选型上的同学可以试一下。

往后看也有几个方向值得追。一是 GELATO 在论文里的另一个用法：projector-only 训完的状态可以当作一个"保留兼容性的初始化"，再往上做更激进的多模态联合训练，是有路径的。二是非文本 encoder 的选型空间还没充分探索过，换不同的 ViT、不同的 audio encoder 进来，配套的 projector 设计能不能进一步抬高曲线，是开放问题。三是视频。temporal reasoning 和 moment retrieval 上 v5-omni 已经不弱，但其他视频任务依旧明显落后，Jina 自己在 future work 里写得很直接：下一版会专门补这块功课。多个模态的 projector 联合训练、而不是各训各的，也在他们要做的实验清单上。

也就是说，v5-omni 是 GELATO 的"第一击"，不是终点。
