# AutoDL FastAPI Deployment

这个目录是给 `AutoDL` 机器准备的独立推理服务。

目标是不用 `vLLM`，而是在 AutoDL 上直接用 `FastAPI + Transformers + Qwen2.5-VL + LoRA` 跑推理。

## 1. 你需要上传到 AutoDL 的文件

把下面这些内容放到 AutoDL 上：

1. 当前目录整个上传：
   - `deployment/autodl_fastapi/app.py`
   - `deployment/autodl_fastapi/requirements.txt`
   - `deployment/autodl_fastapi/start.sh`

2. 你的基座模型目录：
   - 例如 `Qwen2.5-VL-7B-Instruct/`

3. 你的 LoRA 目录：
   - 例如 `kline_lora_v3_lr5e5_ep5/`
   - 如果你想固定某个最佳 checkpoint，也可以直接上传最佳 checkpoint 目录，例如 `checkpoint-1050/`

## 2. 推荐的 AutoDL 目录结构

可以按下面这种方式摆放：

```text
/root/autodl-tmp/
  deploy/
    autodl_fastapi/
      app.py
      requirements.txt
      start.sh
  models/
    Qwen2.5-VL-7B-Instruct/
  adapters/
    kline_lora_v3_lr5e5_ep5/
```

## 3. 安装依赖

在 AutoDL 上进入部署目录后执行：

```bash
cd /root/autodl-tmp/deploy/autodl_fastapi
pip install -r requirements.txt
```

如果你的 AutoDL 环境已经自带合适版本的 `torch`，也可以只安装其它包。

## 4. 启动前需要设置的环境变量

至少要设置这两个路径：

```bash
export KLINE_MODEL_BASE_DIR=/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct
export KLINE_LORA_DIR=/root/autodl-tmp/adapters/kline_lora_v3_lr5e5_ep5
```

推荐再补这些：

```bash
export KLINE_SERVER_HOST=0.0.0.0
export KLINE_SERVER_PORT=6006
export KLINE_MODEL_NAME="Qwen2.5-VL + LoRA"
export KLINE_DEVICE=auto
export KLINE_TORCH_DTYPE=auto
export KLINE_ATTN_IMPLEMENTATION=sdpa
export KLINE_MAX_NEW_TOKENS=160
export KLINE_TEMPERATURE=0.0
```

说明：

- `KLINE_DEVICE=auto`：自动用 GPU。
- `KLINE_TORCH_DTYPE=auto`：有 bf16 就用 bf16，否则用 fp16。
- `KLINE_ATTN_IMPLEMENTATION=sdpa`：兼容性更稳。如果你的环境装好了 flash-attn，也可以改成 `flash_attention_2`。
- `processor/tokenizer` 默认会从基座模型目录加载，不再默认读取 LoRA/checkpoint 目录里的 tokenizer 文件，这样更稳。
- 如果你确实有单独的 processor 目录需要强制指定，可以额外设置：
  `export KLINE_PROCESSOR_SOURCE=/your/processor_dir`

## 5. 启动服务

```bash
cd /root/autodl-tmp/deploy/autodl_fastapi
bash start.sh
```

启动成功后可以访问：

- 健康检查：`http://<AutoDL_IP>:6006/health`
- 推理接口：`http://<AutoDL_IP>:6006/predict`

## 6. 本地项目如何连接这个服务

你的本地项目后端现在已经支持两种远程模式：

- `openai_compat`：旧的 `vLLM /v1/chat/completions`
- `custom_fastapi`：现在这个新的 AutoDL FastAPI 服务

你现在要切到新的方式，所以在本地项目启动前设置：

```powershell
$env:KLINE_INFERENCE_BACKEND="remote_api"
$env:KLINE_REMOTE_API_PROTOCOL="custom_fastapi"
$env:KLINE_REMOTE_API_BASE_URL="http://你的AutoDL公网IP:6006"
$env:KLINE_REMOTE_API_PREDICT_PATH="/predict"
$env:KLINE_REMOTE_API_HEALTH_PATH="/health"
$env:KLINE_REMOTE_API_DISPLAY_NAME="Qwen2.5-VL + LoRA"
```

然后照常启动你本地项目后端：

```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## 7. 手动测试接口

在 AutoDL 机器上可以先用 `curl` 测：

```bash
curl -X POST "http://127.0.0.1:6006/predict" \
  -F "file=@/root/test.png"
```

返回格式类似：

```json
{
  "label": "双底",
  "confidence": 0.78,
  "reason": "图中出现两个相近低点，中间存在明显反弹，符合双底特征。",
  "raw_output": "双底",
  "backend_mode": "Qwen2.5-VL + LoRA"
}
```

## 8. 常见问题

### 8.1 显存不够

先尝试：

- 减小输入图片尺寸
- 把 `KLINE_MAX_NEW_TOKENS` 调小，比如 `96`
- 使用更大的 AutoDL GPU

### 8.2 访问不到 AutoDL 服务

检查：

- AutoDL 端口有没有开放
- 你本地填写的是不是公网 IP
- 服务是不是监听在 `0.0.0.0`

### 8.3 LoRA 目录到底填哪个

优先填“实际要推理的那个目录”：

- 如果你要用最终导出的 LoRA，就填 LoRA 根目录
- 如果你确认最优模型在某个 checkpoint，比如 `checkpoint-1050`，就直接填那个 checkpoint 目录
