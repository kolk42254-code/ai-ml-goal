# Image AI from scratch

Level 1 of building an image-generating AI: a small **diffusion model** (DDPM), written from scratch in PyTorch and trained on images from Hugging Face. It learns from thousands of real images, then draws new ones.

Made with Claude (an AI), so it lives in `Projects_by_AI`. It is a preview of Phase 3 (deep learning, PyTorch), not study code.

<a href="https://colab.research.google.com/github/kolk42254-code/ai-ml-goal/blob/main/Projects_by_AI/image-ai/level1_diffusion_from_scratch.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

| File | What it is |
|---|---|
| [level1_diffusion_from_scratch.ipynb](level1_diffusion_from_scratch.ipynb) | The notebook: noise maths, U-Net, training, generating, sharing on the Hub |

## What you build

1. **Load** images from the Hugging Face Hub with `datasets`: handwritten digits (MNIST), clothes (Fashion-MNIST), or butterfly photos.
2. **Destroy** them with noise, step by step (the forward process).
3. **Build** a U-Net, the neural network that guesses the noise in a noisy image.
4. **Train** it to guess the noise.
5. **Generate** new images: start from pure noise and remove the guessed noise 1000 times.
6. **Check** your maths against Hugging Face `diffusers` (optional).
7. **Share** the model on the Hugging Face Hub (optional).

## Cost

$0. The notebook runs on Google Colab's free GPU (usually a T4). A Hugging Face account is free too.

## How to run

**Google Colab (recommended)**
1. Click the **Open in Colab** badge above.
2. Check **Runtime → Change runtime type → T4 GPU**.
3. Run the cells in order with **Shift + Enter**.

The badge opens the notebook from the `main` branch. If it isn't on `main` yet, download the `.ipynb` file and use **File → Upload notebook** in Colab.

**Kaggle (another free GPU option):** create a new notebook, use **File → Import Notebook** to bring in this `.ipynb`, then turn on a GPU and internet in the notebook settings. Kaggle may ask you to verify your phone number first, and its menus may have changed since this was written.

**Your laptop (CPU only, much slower)**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

```bash
pip install datasets huggingface_hub safetensors matplotlib notebook
```

```bash
jupyter notebook Projects_by_AI/image-ai/level1_diffusion_from_scratch.ipynb
```

In Part 1 of the notebook, switch on the smaller CPU settings.

## Skills this project previews

| In the notebook | Where it is in my plan |
|---|---|
| Classes, inheritance, `super().__init__()` | P66-P74 (Phase 1, now) |
| Tensors, shapes, broadcasting | N1-N14, NumPy (Phase 1) |
| Mean, variance, the normal distribution | M1-M8, M26 (Phase 1) |
| Loss and gradient descent | M40-M47 (Phase 2) |
| Neural networks, backpropagation | NN1-NN9 (Phase 3A) |
| PyTorch and training skills | PT1-PT12, TR1-TR8 (Phase 3A) |
| Convolutions, U-Net | CV1-CV4 (Phase 3B) |
| Sine/cosine position signals | AT1-AT11 (Phase 3B) |
| Hugging Face datasets and Hub | HF1-HF7 (Phase 3B) |

## Next levels

- **Level 1.5:** "draw me a 7" (class conditioning), attention layers, faster sampling (DDIM).
- **Level 2:** fine-tune Stable Diffusion on your own pictures with LoRA, using Hugging Face `diffusers`.
