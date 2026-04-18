import yaml
import importlib
from django.conf import settings
import os

def get_data_adapter():
    config_path = getattr(settings, 'GREEKS_VIZ_CONFIG', {}).get(
        'DATA_SOURCE_CONFIG', 
        os.path.join('greeks_viz', 'config', 'data_source.yaml')
    )
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    module = importlib.import_module(config['adapter_module'])
    return module.Adapter(config.get('params', {}))
