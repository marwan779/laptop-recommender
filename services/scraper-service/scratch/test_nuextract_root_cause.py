import sys, os, json
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')
from pipeline.ai_fallback.nuextract import NuExtractONNXFallbackExtractor
from pipeline.schema import ComponentEnvelope

extractor = NuExtractONNXFallbackExtractor(
    model_id='numind/NuExtract-2.0-2B',
    execution_provider='CUDAExecutionProvider',
    lazy_load=False
)

tests = [
    ('Index 67 ASUS', 'Storage: 1TB M.2 NVMe PCIe 4.0 SSD (Extra M.2 2230 Slot Available)'),
    ('Index 93 MSI', 'Storage: 1TB NVMe PCIe Gen4 SSD (plus 1x 2.5" SATA HDD/SSD expansion slot)'),
    ('Index 121 Lenovo', 'Storage: 512GB M.2 PCIe 4.0 x4 NVMe SSD, with an extra M.2 slot | Storage Interface: M.2 PCIe 4.0 x4 NVMe | Additional Storage: Extra M.2 slot available'),
    ('Index 85 Dell Alienware Audio', 'Camera: 720p HD @ 30 fps, dual-array microphones | Audio: Stereo speakers - 4W total (2W × 2) - Realtek AL3204')
]

for label, ctx in tests[:3]:
    env = ComponentEnvelope(
        component_name='storage',
        raw_spec=ctx,
        sub_schema={'capacity_gb': 1024, 'storage_type': 'SSD', 'interface': 'NVMe', 'form_factor': 'M.2', 'slot_count': None, 'max_supported_gb': None},
        locked_fields={'capacity_gb', 'storage_type', 'interface', 'form_factor'},
        cpu_context=None
    )
    prompt = extractor.format_component_prompt(env, model_id='numind/NuExtract-2.0-2B')
    raw_out = extractor._generate_transformers(prompt)
    print(f'=== {label} ===')
    print('RAW OUTPUT:', raw_out.strip())

# Audio test
env_audio = ComponentEnvelope(
    component_name='audio_webcam',
    raw_spec=tests[3][1],
    sub_schema={'speaker_count': 2, 'webcam_resolution': '720p', 'has_ir_camera': None, 'has_privacy_shutter': None, 'microphone': None},
    locked_fields={'speaker_count', 'webcam_resolution'},
    cpu_context=None
)
prompt = extractor.format_component_prompt(env_audio, model_id='numind/NuExtract-2.0-2B')
raw_out = extractor._generate_transformers(prompt)
print(f'=== {tests[3][0]} ===')
print('RAW OUTPUT:', raw_out.strip())
