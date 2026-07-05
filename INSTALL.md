# AIDLC-MRI Installation Notes

## Reliable Brain-Only 3D Mesh

Final brain-only 3D mesh generation requires a reliable skull stripping tool.
The simple threshold fallback is debug-only and is not used for final 3D output.

Supported tools:

- SynthStrip (`mri_synthstrip`)
- HD-BET (`hd-bet`, `HD_BET`, or `python -m HD_BET`)

## Windows HD-BET Install

Run in PowerShell:

```powershell
python -m pip install --upgrade pip
pip install hd-bet
```

Check installation:

```powershell
where hd-bet
where HD_BET
python -m HD_BET -h
```

If commands are not found, check the virtualenv Scripts folder:

```powershell
.venv\Scripts\hd-bet.exe
.venv\Scripts\HD_BET.exe
```

Restart Streamlit after installing:

```powershell
streamlit run app.py --server.port 8501
```

## SynthStrip

SynthStrip may require FreeSurfer/SynthStrip installation. After installation,
verify:

```powershell
where mri_synthstrip
```

## Debug Fallback

The simple fallback can be used only for 2D overlay/debug preview. It is not
considered brain-only and cannot generate final 3D mesh.
