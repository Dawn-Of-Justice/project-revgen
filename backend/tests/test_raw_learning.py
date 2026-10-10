import json
import pytest
from app.catalog import Catalog
from app.config import settings
from app.learning import LearningStore
from app.schemas import Device, Plan
from app.emitter_protocol import validate_steps, encode_command


def raw(**kw):
    return dict(type="ir", protocol="raw_timings", timings=[3500,1750,450,450,450], carrier_khz=38, repeat=0, **kw)

@pytest.mark.parametrize("field,value", [("timings", []),("timings",[100,100]),("timings",[True,100,100]),("timings",[99,100,100]),("timings",[65001,100,100]),("timings",[100]*513),("timings",[65000]*9),("carrier_khz",29),("carrier_khz",61),("carrier_khz",True),("repeat",1)])
def test_reject_invalid_raw(field,value):
    code=raw();code[field]=value
    assert validate_steps([code])

def test_total_raw_budget():
    code=raw();code["timings"]=[450]*257
    assert validate_steps([code]) is None
    assert validate_steps([code,code]) == "too many raw timings"

def test_raw_mapping_survives_storage_catalog_and_wire(tmp_path):
    store=LearningStore(tmp_path/"learned.json")
    payload=dict(id="capture-raw-01",producer="emitter-0001",sequence=1,kind="command",device="tv",device_name="TV",action="volume_up",name="Volume",behavior="button",code=raw())
    assert store.accept(json.dumps(payload).encode())["ok"]
    catalog=Catalog.load(settings.catalog_path)
    LearningStore(store.path).apply(catalog)
    step=catalog.step(Device.TV,"volume_up")
    wire=json.loads(encode_command(Plan(id="raw-test",steps=[step]),"revgen/emitter/cmd"))
    assert wire["steps"][0]==raw()
