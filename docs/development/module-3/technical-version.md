# 四六级听力系统一期：统一技术版本文档

| 项目 | 固定内容 |
|---|---|
| 文档版本／日期 | V1.2／2026-11-06；全项目统一版本入口 |
| 技术证据日期 | 2026-11-04；本次沿用已有版本、锁文件与核查记录，未重新查询远端或发行版本 |
| 适用范围 | 四六级听力系统一期全部模块；统一管理前端、后端、数据库、处理环境、模型及开发工具版本 |
| 模块三业务需求 | [模块三需求文档](../../requirements/module-3/requirements.md)；纯后端自动处理与实际入库 |
| 版本来源提交 | 2026-11-04 核实的远端 `develop`：`b965a0f3771c9f6212be29b65fda326ce0307b11`；保留为版本来源，不声称是 2026-11-06 的最新分支头 |
| 处理路线 | 默认提取并核对答案原文/提问 → 固定来源句子 → 本地WhisperX CPU强制对齐 → 停下核听确认 → 确认后组装、DeepSeek候选标注及待审入库；ASR仅显式无原文模式启用 |
| 沿用技术冻结编号 | `M3-WIN64-1.1.0`；保留已有锁文件与配置身份，适用范围扩展不另改编号 |
| 目标平台 | Windows x64，常规 GIL 版 CPython；不使用 `cp313t/cp314t` 自由线程构建 |
| 既有完成记录（2026-11-04） | 仓库依赖核对、官方版本及分发文件查询、三个环境的完整依赖解析和哈希锁定、模型 revision 与资源清单固定 |
| 既有记录未完成（截至 2026-11-04） | 目标环境安装、DLL 实际加载、GPU 推理、OCR 识别、DeepSeek 实际调用、数据库迁移与模块三业务验收；后续实施状态查对应日期记录 |

本文是全项目开发采用的统一版本依据。具体版本表、锁文件和模型清单沿用模块三 V1.1 基线；本次不升级依赖、不重新解析锁文件，也不据文档统一认定整套环境已安装或质量已达标。锁定文件已包含间接依赖，不能再将仓库原有的直接依赖列表称为完整环境锁文件。2026-11-04盘点时原工作区存在未提交修改，属于历史观察；2026-11-06原仓库已在develop且干净，模块三在独立开发目录实施。本次文档同步不改写代码、依赖锁或数据库。

V1.1 按用户决定将 API 从 Python 3.14.10 统一到 **3.13.16**。API、ASR、OCR 现在共用同一解释器版本，继续保留三个独立虚拟环境。已按新目标重新解析后端依赖，39 个包的版本未发生变化；旧 API 锁和配置保留在附件 `history/M3-WIN64-1.0.0/`。此次仅更新文档、锁文件及基线配置，未安装或切换实际运行环境。

2026-11-06流程说明按需求V1.8及开发V1.4同步：已有完整原文不默认转写，缺原文先待补充；默认stop_after=align。预算及正文起止分别≤300ms已确认，精度须真实核听。原文对齐由WhisperX加载固定模型，本地m3.reference-ctc.v2适配层区分发音、空白和标点，自动扩窗重试；使用已冻结的TorchAudio2.8.0+cu128，方法代码哈希单独记录。此处澄清处理分支，不变更V1.2组件版本、模型revision、锁文件或冻结编号。实际组件运行和完整链路验收以[对齐复核记录](alignment-review.md)分别报告；后文2026-11-04盘点保留历史身份，不表示目前仍未安装或运行。

## 统一使用规则与模块适用范围

本文件作为一期全部模块的技术版本总入口。模块一、二和后续模块共用的后端、数据库、前端及工具版本均以本文和对应锁文件为准；模块需求、开发设计继续负责业务范围与接口约定。历史文档中的不同版本保留为历史记录，新增开发和环境重建引用本文件。

| 范围 | 采用内容 | 使用边界 |
|---|---|---|
| 模块一：认证与页面框架 | 第二节后端和数据库、第八节前端及工具 | 后端 Python 统一为 3.13.16；历史运行结论须在新环境复验 |
| 模块二：题库、整卷与媒体接口 | 同一后端、数据库和前端基线 | 复用 API 锁及前端 package-lock；迁移、接口和媒体访问另做回归 |
| 模块三：自动处理与入库 | API、ASR、OCR 三套环境，第三至七节的模型、原生库和参数 | 保留独立进程与环境；不将模块三的纯后端范围扩展为整个项目不开发前端 |
| 后续模块 | 复用已有共用技术版本 | 新增依赖或变更版本时同步修订本文及受影响锁文件；尚未选型的组件不视为已冻结 |

后端模块共用 API 环境；仅执行音频与文档处理的进程需要 ASR／OCR 环境。前端按既有 `package-lock.json` 重建，其他模块无需因本文件而安装全部识别依赖。各版本的功能及兼容性验收仍按模块分别记录。

**日期口径：** 除本节和修订记录外，下文的查询、解析、本机观察及“本次”均沿用 2026-11-04 原记录。本次仅统一文档范围与入口，不重新判断这些历史观察是否仍是当前状态；2026-11-05 等后续开发或安装记录也不被旧记录覆盖。

| 文档修订 | 日期 | 内容 |
|---|---|---|
| 原模块三 V1.0 | 2026-11-04 | 初始技术冻结 `M3-WIN64-1.0.0`，旧 API 锁保留在附件 history 目录 |
| 原模块三 V1.1 | 2026-11-04 | API 与 ASR、OCR 统一 Python 3.13.16；冻结编号 `M3-WIN64-1.1.0` |
| 全项目 V1.2 | 2026-11-06 | 提升为一期全部模块的统一版本文档；组件版本、锁文件、模型 revision 和配置保持原基线 |

原始依据：模块三开发技术版本基线 V1.1（历史正文）（历史本地资料，随验收证据另行交接）。配套附件继续使用原目录与文件名，避免破坏既有引用、校验和及批次追溯。

## 一、版本决定与环境隔离

采用三个独立 Python 环境。API 负责鉴权、任务与结果接口；ASR 处理进程负责本地音频、DeepSeek 调用及入库服务；OCR 子进程负责 PDF／图片提取。通过受控文件和结构化结果传递数据，不让 API 服务导入全部深度学习依赖。

| 环境 | Python 精确版本 | 主要内容 | 锁定文件 |
|---|---|---|---|
| API | **3.13.16** | FastAPI、认证、数据库、迁移和测试 | [requirements-api.lock.txt](../../../backend/config/module3/requirements-api.lock.txt) |
| ASR／处理进程 | **3.13.16** | 默认WhisperX CPU原文对齐；显式无原文模式才用faster-whisper/CUDA；确认后DeepSeek HTTP调用及待审入库 | [requirements-asr.lock.txt](../../../backend/config/module3/requirements-asr.lock.txt) |
| OCR／文档 | **3.13.16** | PaddleOCR、CPU PaddlePaddle、PDF 提取／渲染和核对文件 | [requirements-ocr.lock.txt](../../../backend/config/module3/requirements-ocr.lock.txt) |

WhisperX 3.8.6 声明 Python `>=3.10,<3.14`，本次统一使用的 3.13.16 满足该范围。其 PyTorch、TorchAudio、TorchVision 分别限制在 2.8、2.8、0.23 版本线。[指定版本元数据](https://pypi.org/pypi/whisperx/3.8.6/json)。

后端、音频和 OCR 均固定 Python **3.13.16**，方便统一准备解释器；三个环境分开安装各自依赖。旧资料中的 3.14.2、3.14.3 及模块二交付记录的 3.14.10 保留为历史或环境观察，不再作为全项目 API 目标。此次后端解释器从 3.14 改为 3.13，已有模块一、二必须在新目标环境重新验证，不能沿用旧环境的运行结论。官方已发布后续 3.13 安全版本，但它们不应被描述为本次已验证的 Windows 二进制替代；将来更换解释器补丁版须另记构建来源并复验。[Python 3.13.16](https://www.python.org/downloads/release/python-31316/)。

## 二、后端与数据库固定版本

除补齐 Starlette、测试客户端与 Ruff 外，保留远端 `develop` 的所有后端直接依赖版本；本次不因模块三另换 Web 框架、认证或数据库访问体系。

| 技术／包 | 固定版本 | 用途／说明 |
|---|---|---|
| PostgreSQL 服务端、pg_dump、psql | **18.6** | 延续模块二；备份工具与服务端同版本线，数据库时间按需求以 UTC 保存 |
| fastapi | **0.143.0** | API 框架，继承仓库 |
| starlette | **1.7.0** | 显式固定旧技术报告核对的版本线，避免原 requirements 范围解析到其他版本 |
| uvicorn | **0.54.0** | API 服务器，继承仓库 |
| pydantic／pydantic-core | **2.14.1／2.50.1** | 接口及处理结果字段检查 |
| pydantic-settings | **2.16.2** | 配置读取 |
| SQLAlchemy | **2.1.4** | 复用模型、会话及事务 |
| alembic | **1.20.0** | 增量迁移，不重建旧认证表 |
| psycopg／psycopg-binary | **3.3.6／3.3.6** | 使用 `psycopg[binary]`，不临时改为 psycopg2 |
| PyJWT | **2.15.1** | 现有 JWT 认证 |
| bcrypt | **5.0.0** | 现有口令哈希 |
| python-dotenv | **1.2.4** | 配置文件加载；不能假设 Python 会自动读取 `.env` |
| httpx | **0.28.1** | 现有 HTTP 工具及 DeepSeek 请求 |
| pytest／pytest-asyncio | **9.2.0／1.4.1** | 后端回归验证 |
| httpx2 | **2.13.1** | Starlette 1.7 测试客户端所需的另一发行包，不替换上面的 httpx |
| Ruff | **0.17.0** | 全项目后端开发目标为 `py313`；仓库原配置仍为 `py314`，开发落地时调整并验证，此次未修改旧工作区 |

后端直接依赖来源为[基线 requirements](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/requirements.txt)。Starlette 1.7 的测试客户端实际导入 `httpx2` 并有兼容分支，不能把“安装了 httpx 0.28”当作已经满足该测试入口。[Starlette 1.7 源码](https://github.com/Kludex/starlette/blob/1.7.0/starlette/testclient.py)。PostgreSQL 18.6 为已发布版本，继续使用该基线，不自动升级 19 RC。[官方发行记录](https://www.postgresql.org/docs/release/18.6/)。

## 三、本地转写、对齐与 GPU 固定版本

| 技术／包 | 固定版本 | 决定依据与使用边界 |
|---|---|---|
| faster-whisper | **1.2.1** | 可选本地原音转写，仅显式无原文模式启用 |
| WhisperX | **3.8.6** | 默认CPU强制对齐已核对原文，保持来源句子和ID；最终必交为句级时间 |
| CTranslate2 | **4.8.3** | faster-whisper 推理引擎，固定 Windows cp313 wheel |
| torch | **2.8.0+cu128** | CUDA 12.8 构建，固定官方 Windows cp313 wheel URL 与 SHA-256 |
| torchaudio | **2.8.0+cu128** | 与 torch 配套 |
| torchvision | **0.23.0+cu128** | WhisperX 的声明依赖，不因没有图像业务而擅自删除 |
| torchcodec | **0.7.0** | 选 PyPI 的 Windows cp313 wheel；不用 CUDA 索引中仅供 Linux 的同名构建 |
| pyannote.audio | **4.0.7** | WhisperX 依赖；本期不启用额外说话人分离任务，不增加受限说话人模型下载 |
| av（PyAV） | **15.1.0** | 固定提供 cp313 Windows wheel 的版本；不沿用旧报告中发生参数异常的 av 19 组合，也不宣称本次已证明异常修复 |
| transformers | **4.57.1** | 固定 4.x，配合下列 Hugging Face Hub 版本 |
| huggingface-hub | **0.36.0** | 满足 WhisperX `<1.0.0`，不能直接装查询时最新的 2.4.0 |
| tokenizers | **0.22.2** | 依赖解析后固定 |
| numpy | **2.2.6** | 满足 WhisperX 下界及本次解析的数值依赖；OCR 单独环境同样固定 |
| nltk | **3.10.4** | 分句依赖；数据资源另行固定，见第五节 |
| onnxruntime | **1.31.1** | faster-whisper 依赖，固定 CPU 发行包用于相关本地组件 |
| pandas／scipy | **3.1.0／1.18.1** | 作为解析出的间接依赖固定；不代表新增业务功能 |
| nvidia-cublas-cu12 | **12.8.4.1** | 明确固定 NVIDIA Windows 运行库 wheel，避免仅凭本机偶然可用的 DLL |
| nvidia-cudnn-cu12 | **9.10.2.21** | 明确固定 cuDNN 9 运行库 wheel；实际搜索路径仍需新进程验证 |

PyTorch 官方提供 `2.8.0／0.23.0／2.8.0` 与 CUDA 12.8 的配套安装组合；本次进一步指定 `+cu128`，避免误取 CPU 或其他 CUDA 构建。[官方历史版本说明](https://pytorch.org/get-started/previous-versions/)。WhisperX 和 pyannote 的声明共同限制 torchcodec 在 `>=0.7,<0.8`；本次固定已存在的 0.7.0，不将其写成未来也只能使用这一版本。[WhisperX 元数据](https://pypi.org/pypi/whisperx/3.8.6/json)、[pyannote.audio 元数据](https://pypi.org/pypi/pyannote.audio/4.0.7/json)。

仅可选ASR路线要求的CTranslate2 CUDA、cuDNN条件与PyTorch wheel是两层问题；默认原文CPU对齐不以GPU转写验证为前置。“torch 能用 GPU”不能代替 CTranslate2 推理验证。NVIDIA 两个运行库的 Windows 发行文件已查询，包版本和 SHA-256 已纳入 ASR 锁。[CTranslate2 官方安装说明](https://opennmt.net/CTranslate2/installation.html)、[cuBLAS 发行元数据](https://pypi.org/pypi/nvidia-cublas-cu12/12.8.4.1/json)、[cuDNN 发行元数据](https://pypi.org/pypi/nvidia-cudnn-cu12/9.10.2.21/json)。

默认采用固定原文直接CPU对齐。仅显式无原文路线的转写配置固定为 `large-v3`、`language=en`、`task=transcribe`、CUDA `int8_float16`、`beam_size=5`、单任务／批量 1；对齐默认 CPU，降低同时占用显存的需求。统一输入 16kHz、单声道、float32，保留切块到原音绝对毫秒的偏移。WhisperX 可产生词级中间结果，最终按需求整理为句级片段，不增加词级 20ms 验收指标。完整默认参数见[处理配置](../../../backend/config/module3/processing-profile.json)。

## 四、音频原生组件与驱动

| 对象 | 固定基线 | 管理方式 |
|---|---|---|
| FFmpeg／FFprobe 命令行 | **7.1.1，GyanD full_build-shared Windows x64** | 固定完整 ZIP 分发包；在项目受控目录使用绝对路径 |
| torchcodec 共享库来源 | **同一 FFmpeg 7.1.1 shared 分发包的 bin 目录** | `FFMPEG_DLL_DIR` 指向该目录；新进程中在导入前注册，并保留 DLL 目录句柄 |
| PyAV 自带的 FFmpeg 库 | **随 av 15.1.0 Windows wheel 固定** | 由 wheel 哈希间接冻结；不手工用上行 DLL 覆盖 wheel 自带库 |
| CUDA 构建线 | **12.8（cu128）** | 固定 PyTorch wheel 和上述 cuBLAS／cuDNN wheel，不按 `nvidia-smi` 显示值反推安装了哪个 Toolkit |
| CUDA Toolkit 补充安装基线 | **12.8 Update 1（12.8.1）** | 仅实际工具或缺库场景需要时采用；纯预编译 wheel 路线不因本表强制安装完整编译工具链 |
| NVIDIA 驱动参考基线 | **580.88** | 本机已观察；其他机器须记录实际驱动并复验，不为对齐文档强制回退驱动 |

FFmpeg 固定[发行方 7.1.1 shared 构建](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1)，其归档、CLI 和 bin 中 DLL 的 SHA-256 见[FFmpeg 产物清单](../../../backend/config/module3/ffmpeg-artifact-manifest.json)。该自包含分发包替代本轮新建 Conda FFmpeg 环境，避免只锁主包而漏掉 Conda 原生依赖；原报告中已存在的 Conda 环境不删除、不改写。PyAV 使用其发行 wheel 原有打包方式。[PyAV 15.1 分发说明](https://pypi.org/project/av/15.1.0/)。CUDA 的各子库独立编号，因此不能把 `12.8.1` 当作所有 DLL 的统一版本。[NVIDIA 12.8.1 发行说明](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html)。

本机当前可解析的 FFmpeg 是 **9.0 full shared**，不是本节的目标版本。开发时为模块三配置独立的 7.1.1 目录，不全局清理或覆盖已有 FFmpeg。标准解码入口使用固定torchcodec将音频规范化，默认连同原文传入CPU对齐；仅可选ASR路线先向faster-whisper传递波形；PyAV 内置解码单独补测，不能仅凭版本选择宣称故障已经排除。多个解码组件在同一处理进程中使用时，核查实际加载路径及所需导入顺序。

## 五、模型文件与分句资源固定

模型不只固定名称，还固定仓库 revision。以下完整提交号已通过发布者模型仓库 API 查询；大权重 SHA-256 取自发布者 LFS 元数据，小配置文件已读取并计算哈希。2026-11-04版本盘点未下载几GB模型或执行推理；后续安装及2026-11-06原文对齐实跑见前述记录，不以此历史说明覆盖后续证据。

| 作用 | 模型／资源 | 固定 revision |
|---|---|---|
| 转写 | `Systran/faster-whisper-large-v3`，CT2 格式 | `edaa852ec7e145841d8ffdb056a99866b5f0a478` |
| 英文对齐 | `jonatasgrosman/wav2vec2-large-xlsr-53-english` | `569a6236e92bd5f7652a0420bfe9bb94c5664080` |
| OCR 文本检测 | `PaddlePaddle/PP-OCRv5_server_det` | `ca867c897ecbca8873081573a802ad70d499cb94` |
| OCR 中英文字识别 | `PaddlePaddle/PP-OCRv5_server_rec` | `b26c3587fda8da3c8ec0ce357214b4d661ff1558` |
| NLTK `punkt_tab` | `nltk/nltk_data` 的对应 ZIP | `4f15a3d89eefe9748ec1c05be495d91289197155` |

完整文件 URL、大小、SHA-256 及“已下载／仅元数据核实”状态见[模型产物清单](../../../backend/config/module3/model-artifact-manifest.json)和[NLTK 资源清单](../../../backend/config/module3/nltk-resource-manifest.json)。NLTK ZIP 已下载并计算哈希，部署时解压到受控 `NLTK_DATA/tokenizers/punkt_tab/`，不在任务启动时临时联网下载。

模型依据分别为[转写模型发布页](https://huggingface.co/Systran/faster-whisper-large-v3)、[英文对齐模型发布页](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-english)、[Paddle 检测模型](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_det)、[Paddle 识别模型](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec)。下载后使用本清单校验，任务从固定本地路径加载，不追踪 `main/latest`；不能用“缓存里已经有同名模型”代替哈希核对。

## 六、PDF、扫描件与核对文件固定版本

| 技术／包 | 固定版本 | 决定 |
|---|---|---|
| PaddleOCR | **3.7.0** | 本期采用固定版式的文本检测与识别入口 |
| PaddleX | **3.7.2** | `paddleocr 3.7.0` 声明的 `>=3.7,<3.8` 范围内显式固定 |
| PaddlePaddle | **3.3.1，CPU 包** | 单独 OCR 环境，不与 PyTorch 抢 GPU；已核实 cp313 Windows wheel |
| pdfplumber | **0.11.10** | 文本 PDF 的文字与位置提取 |
| pdfminer.six | **20260107** | pdfplumber 指定的解析依赖 |
| pypdfium2 | **5.14.0** | PDF 页面渲染，固定 300 DPI 作为初始处理配置 |
| opencv-contrib-python | **4.10.0.84** | PaddleX 依赖；不同时额外装另一套同名 cv2 提供包 |
| Pillow | **13.0.0** | 页面／图片处理，按锁文件固定 |
| openpyxl | **3.1.5** | 核对、导出和既有采集结构辅助；不能代替实际入库 |
| numpy | **2.2.6** | OCR 环境单独固定 |

PaddleOCR 的直接依赖范围与 PaddlePaddle 的 Windows 文件列表均已查询，不能仅以 README 的旧徽标判断 Python 支持范围。[PaddleOCR 3.7.0 元数据](https://pypi.org/pypi/paddleocr/3.7.0/json)、[PaddlePaddle 3.3.1 元数据](https://pypi.org/pypi/paddlepaddle/3.3.1/json)。

默认关闭文档方向分类、去畸变、文本行方向分类和 oneDNN，不额外拉取这些模型；固定版式中的题号、选项及页码归属由处理逻辑核对。若真实扫描样例需要方向纠正或复杂版面模型，应以独立配置修订记录新增模型及 revision，再复验。**PP-StructureV3 不作为本次默认安装及模型入口**；扫描件必验要求保留，不把未启用复杂版面模型等同于免验 OCR。

PyMuPDF、RapidOCR、Pandera 不列入本轮默认环境：PDF 提取和渲染已有对应工具；OCR 不同时装两套路线；结构校验复用 Pydantic 和跨表规则。后续确需新增时补版本与影响说明，不由原报告提及自动变成本期依赖。

## 七、DeepSeek API 与标注配置固定

| 项目 | 固定值 |
|---|---|
| 服务／入口 | DeepSeek 官方 API，`https://api.deepseek.com/chat/completions` |
| 请求型号 | **`deepseek-flash`** |
| 调研时官方对应模型 | **DeepSeek-V4.1-Flash-1017** |
| HTTP 客户端 | **httpx 0.28.1**；直接发 HTTP 请求，不新增 OpenAI SDK 或其他厂商 SDK |
| 输出 | `response_format={"type":"json_object"}`，`stream=false` |
| 初始推理参数 | `thinking={"type":"disabled"}`、`temperature=0`、`max_tokens=4096` |
| 并发／失败处理配置 | 并发 1、单次请求超时 120 秒、最多重试 2 次；截断、空内容和结构失败须记录并进入有限重试或待确认 |
| 标注对象 | 已提取文字、题目、来源明确的答案解析、已有片段编号及固定词典；原始音频在本地处理 |

型号及官方当日对应版本依据[模型说明](https://api-docs.deepseek.com/quick_start/pricing/)，JSON 与推理参数依据[JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)和[思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)。以上是开发配置决定，未使用真实账号测评其教学标注质量或产生调用费用。

**外部 API 不能获得与本地权重一样的不可变版本保证。** 官方请求名是服务别名，不能把展示的 `DeepSeek-V4.1-Flash-1017` 自行当作另一个可调用的固定 snapshot ID。冻结请求型号和参数，同时保存官方说明快照、请求／响应模型字段、用量、输入输出和实际调用时间；提示词、字段结构、词典及方法各有版本和内容哈希。发现服务模型映射变化时标记新的方法版本并复核，不继续宣称与旧批次完全同模型。温度为 0 也不保证逐字复现。

词典结构固定到最新确认的 16 表快照，SHA-256 为 `6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580`。提示词的具体业务文案在开发时编写，形成后记录文本哈希；该待办不等同于重新选择模型供应商。

## 八、已有前端与开发工具版本

模块三的本轮范围不开发前端；全项目其他模块的前端开发仍采用本节版本。为避免“整个项目版本”与仓库现状冲突，保留现有 React 工程清单，不照搬旧报告中的 Vue、Element Plus、Pinia 或 pnpm。直接依赖已逐项查询 npm registry，完整前端传递依赖继续以基线提交中的 `package-lock.json` 为准，不重新解析升级。

| 技术／包 | 固定版本 |
|---|---|
| Node.js／npm | **24.14.0／11.9.0**，延续仓库 README 的目标版本 |
| React／React DOM | **19.3.1／19.3.1** |
| react-router-dom | **7.18.5** |
| Ant Design／@ant-design/icons | **6.6.8／6.3.4** |
| axios | **1.21.0** |
| Vite／@vitejs/plugin-react | **8.3.5／5.2.0** |
| TypeScript | **6.0.3** |
| @types/react／@types/react-dom | **19.3.0／19.3.0** |
| uv（锁定清单工具） | **0.12.2**，本次实际执行版本 |
| pip（若采用 pip 安装入口） | **26.3**，已核实发行；不是应用运行依赖 |
| Git 参考工具版本 | **2.53.0.windows.2**，本机实际执行版本；仓库内容由提交号固定 |

来源为[基线 package.json](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/frontend/package.json)、[Node 24.14.0 校验清单](https://nodejs.org/download/release/v24.14.0/SHASUMS256.txt)及保存的npm 元数据（历史本地资料，随验收证据另行交接）。不要求为纯后端模块重新安装或构建前端；后续需要时使用 `npm ci` 按锁文件安装。

Redis、Celery、APScheduler、sqladmin、WaveSurfer、Docker、对象存储 SDK、额外前端维护工具不列为本期必装组件。任务由已有后端创建、独立进程执行；校正按既定工具／文件流程，不因旧报告出现管理页面就增设后台 UI。

## 九、锁文件、来源与历史验证结果（2026-11-04）

三个锁文件在 Windows x64 目标上分别解析，使用可用 wheel，包含直接和传递依赖的精确版本及 SHA-256。GPU 三个包进一步写成官方 cp313 Windows wheel 的直接 URL，确保普通安装器也不会到 PyPI 寻找不存在的 `+cu128` 包。源配置与生成命令见ASR 解析配置（历史本地资料，随验收证据另行交接）和解析结果记录（历史本地资料，随验收证据另行交接）。[uv 锁定说明](https://docs.astral.sh/uv/pip/compile/)、[uv PyTorch 源配置说明](https://docs.astral.sh/uv/guides/integration/pytorch/)。

| 检查 | 结果 | 结论边界 |
|---|---|---|
| 远端 develop 与当前需求基线 | 一致 | 只证明本次查询时的提交状态 |
| 仓库后端直接依赖发行版本 | 逐项查询成功 | 不代表目标环境已安装 |
| API 完整解析 | **39 个包，通过** | 已重新按 Python 3.13.16／Windows x64 解析；包版本与 V1.0 相同 |
| ASR 完整解析 | **119 个包，通过** | Python 3.13.16／Windows x64，含固定 CUDA wheel 与运行库 |
| OCR 完整解析 | **76 个包，通过** | Python 3.13.16／Windows x64／CPU Paddle |
| 前端直接依赖发行版本 | 11 项查询成功 | 保留已有锁，不构成本轮构建复验 |
| 模型文件 | revision、发布者权重哈希及小配置哈希已记录 | 未下载全部大模型权重或执行识别 |
| FFmpeg 分发包、NLTK 数据 | 归档及文件哈希见资源清单 | 下载校验不等于 DLL 已实际加载或功能通过 |
| 本地处理、OCR、DeepSeek、入库 | **本次未执行** | 不能据版本冻结宣称整套链路通过 |

ASR 中有 3 个 `0.66b2` 的 OpenTelemetry 间接依赖，是其稳定上层发行包使用的版本编号；已被精确锁定，不是允许 WhisperX 或其他核心组件任意采用预发布版本。其余完整传递包以锁文件为准。

本次解析使用工具环境的 Python **3.14.3** 驱动 uv，并显式指定三个环境的目标 Python **3.13.16** 和 Windows 平台、禁止源码构建。日志中“目标解释器未安装，使用当前解释器处理元数据”的提示，不表示将任一环境的目标改为 3.14，也不表示已在 3.13.16 执行安装。锁文件中的依赖、模型及原生库仍须在目标环境完成实际验证。

本次还发现并排除了两种锁定错误：统一套 `--torch-backend cu128` 会把 torchcodec 定位到没有匹配 Windows wheel 的构建；只输出 `torch==2.8.0+cu128` 而遗漏源配置，会造成重装时找不到 GPU 包。最终锁中仅将 torch、torchaudio、torchvision 指向官方 CUDA 源，并将具体 Windows URL 与哈希写入安装清单。

## 十、历史本机观察、安装边界与后续复验（2026-11-04）

| 本次观察对象 | 实际情况 | 与目标基线的关系 |
|---|---|---|
| 系统 | Windows 11 x64，24H2，build 26100.3194 | 作为本轮参考平台；不强制其他机器回退系统补丁 |
| 本次工具解释器 | Python 3.14.3；工具环境内 FastAPI 0.141.1、Starlette 1.4.1 | 是运行本次研究工具的环境，不是项目已安装的目标环境，不原地升级 |
| Python Launcher | 可见 3.14 与 3.10；未见 3.13.16 | 后续准备同一 Python 3.13.16，再分别创建 API／ASR／OCR 环境 |
| GPU／驱动 | RTX 5060 Laptop，8151 MiB／580.88 | 支持开展 GPU 试跑的资源记录，未实际测试该模型 |
| PostgreSQL 二进制 | `E:\postgresql\bin\postgres.exe` 返回 18.6 | 只查版本，本次未连接数据库或确认迁移进度 |
| FFmpeg | 当前路径解析为 9.0 full shared | 保留现有工具，项目独立配置 7.1.1 |
| Node／npm | 24.13.0／11.6.2 | 与前端目标 24.14.0／11.9.0 不同；本期不触碰前端环境 |
| 本地仓库 | `pr-5` 且有原有未提交修改 | 研发从最新 develop 建立隔离工作区，避免覆盖这些修改 |

正式安装从独立环境开始，使用本附件锁文件和哈希模式；不以解除版本约束、混用镜像或全局替换 DLL 的方式绕过失败。安装后分别记录：依赖检查，FFmpeg CLI，torchcodec／PyAV 的 WAV 与 M4A 解码，WhisperX CPU原文对齐，可选ASR路线另验证CTranslate2 GPU转写，扫描件 OCR，DeepSeek 结构化响应，再进行 PostgreSQL 入库和接口回归。最后补同平台干净环境重建记录。

创建好指定解释器的三个独立环境后，安装入口使用 `uv pip install --python <该环境的 python.exe> --require-hashes --only-binary :all: -r <对应锁文件的绝对路径>`。这条命令是后续开发的操作说明，本次未执行。三个环境均先核对 Python **3.13.16**；不能让工具自动选择当前其他环境的 Python 后继续安装。后端代码检查目标同步为 `py313`，并重跑模块一认证、模块二数据库／迁移／题库及媒体接口验证。前端如需重建则按原工程执行 `npm ci`，本次不重新生成前端锁。

后续若发现实际运行问题，保留失败日志，修订受影响的环境锁和本文件版本；不能静默升级一个包，继续沿用当前冻结编号。依赖解析、安装运行、内容质量及整套验收分别记录。

## 十一、交付文件索引

版本文档之外，配套材料位于 module3-version-freeze-20261104（历史本地资料，随验收证据另行交接）：

- 三套 `requirements-*.lock.txt`：可供后续安装的带哈希完整锁；`requirements-*.in` 为人读入口，ASR 的解析源以 `asr-profile/pyproject.toml` 为准。
- `pypi-release-metadata.json`、`additional-release-metadata.json`、`native-and-api-metadata.json`：本次查询的官方发行元数据、文件及依赖声明。
- `pytorch-windows-wheels.json`、`model-artifact-manifest.json`、`nltk-resource-manifest.json`、`ffmpeg-artifact-manifest.json`：平台包、模型和外部资源的具体来源及校验信息。
- `processing-profile.json`：本地模型、OCR 与 DeepSeek 的初始固定参数，无密钥。
- `backend-baseline-requirements.txt`、`frontend-baseline-package.json`、`frontend-baseline-package-lock.json`：固定仓库提交的依赖快照。
- `resolution-results.json`、`resolve-*.log`、`observed-environment.json`：解析命令、结果及本机观察。
- `artifact-checksums.json`：上述交付文件的哈希索引。

本文件固定的是当前开发版本与来源。本次没有购买资源、调用收费模型、修改运行环境或执行数据库迁移。


## 2026-11-06：自动原文准备的英文OCR资源补充

本节在V1.2冻结软件基线上增加一项模型资源，不修改三套Python解释器、依赖锁或既有模型字节。历史冻结附件继续保持原哈希；现行方法快照必须使用开发目录更新后的`backend/config/module3/model-artifact-manifest.json`，因此不能复用旧方法的通过状态。

- 资源：`PaddlePaddle/en_PP-OCRv5_mobile_rec`，revision `267c36e24c331595590fe7bd72bde2436fd286f2`，Apache-2.0，4个运行文件合计8,004,446字节；逐文件SHA-256和固定下载URL见当前manifest。
- 用途：扫描答案的英文正文和提问识别；原`PP-OCRv5_server_rec`继续用于中文标题，原检测器保留为排版定位备用。CPU、4线程、关闭MKLDNN；运行时禁止自动下载或跟随main。
- 来源：[PaddlePaddle官方模型库固定revision](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec/tree/267c36e24c331595590fe7bd72bde2436fd286f2)。程序记录全部来源和实现哈希，识别失败或定位低可信时停在待确认状态，不启用历史转写补全。



### 同日补充：复用PaddleOCR/PaddleX原生文档能力

自动原文路线的主路径采用已有PaddleOCR 3.7.0/PaddleX 3.7.2的TextDetection、SortQuadBoxes、CropByPolys及TextRecognition，不再以自写像素投影、词典分词、字符列补空格作为生产输入。低可信正文停止，不对原文做词典猜改。

新增检测资源`PaddlePaddle/PP-OCRv5_mobile_det`，revision `0d63e78e2b680928f6b1747d76a08db6e645efb7`，Apache-2.0，4个文件合计4,926,488字节；固定URL及SHA-256见当前manifest。1536像素检测上限、CPU四线程和MKLDNN关闭设置不变，原服务器检测器保留供通用OCR路线使用。[官方固定模型](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det/tree/0d63e78e2b680928f6b1747d76a08db6e645efb7)，[官方文本检测文档](https://www.paddleocr.ai/main/en/version3.x/module_usage/text_detection.html)。裁图和排序调用方式核对了本地锁定版本的`paddlex/inference/pipelines/ocr/pipeline.py`。
