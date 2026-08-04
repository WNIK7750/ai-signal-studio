# 03-02 数据、Artifact 与图片

## 1. 核心数据对象

- SourceConfig；
- CollectionRun；
- RawItem；
- IntelligenceItem；
- EventCluster；
- ReviewBatch；
- ReviewDecision；
- PosterDraft；
- RenderedArtifact；
- AgentPackVersion；
- CapabilityInvocation；
- GraphRun；
- TranscriptionSession。

## 2. Artifact 统一模型

文档、图片、生成的卡片和导出文件使用统一引用：

```python
class ArtifactRef(BaseModel):
    artifact_id: str
    media_type: str
    filename: str
    storage_uri: str
    sha256: str
    size_bytes: int
    created_at: datetime
```

实时语音流不作为普通 Artifact 自动保存。只有用户明确选择“保留录音”时才另行设计，第一版不实现。

## 3. 文档导入

轻量格式优先原生解析：

- Markdown；
- Plain text；
- JSON/YAML；
- Agent Pack ZIP。

复杂 PDF/Office 文件通过 `DocumentParser` Protocol 接入 Docling Adapter，但不是系统硬依赖。

## 4. 图片能力

第一版图片用于：

- 作为情报附件；
- 作为卡片素材；
- OCR；
- Vision 描述；
- 与 IntelligenceItem/PosterDraft 关联。

接口：

```python
class ImageAnalyzer(Protocol):
    async def analyze(
        self,
        artifact: ArtifactRef,
        options: ImageAnalysisOptions,
    ) -> ImageAnalysisResult: ...
```

## 5. 存储

第一版：本地文件系统。

```text
data/artifacts/<workspace>/<yyyy>/<mm>/<artifact-id>/<filename>
```

预留 `ArtifactStorage`：

- LocalArtifactStorage；
- S3ArtifactStorage（后续）。

数据库只保存元数据和 URI，不保存大文件二进制。

## 6. 删除

- 普通“删除”设置状态为 archived/rejected；
- 文件物理删除属于高风险能力；
- 引用中的 Artifact 不得被静默物理删除；
- 定期清理作为后续维护任务。
