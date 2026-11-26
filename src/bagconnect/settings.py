from .bag_handoffs.contracts import Field

EXPOSURE_UNIT = '未确认快速转运行李'
TITLE = '航站行李联程补救'
ROLE = '行李中转席位员'
OBJECT = '联程转运单'
TARGET = '转运未赶上'
ALGORITHM = '正则化逻辑回归'
MODE = 'classification'
IS_SURVIVAL = False
MODEL_EPOCH = 'bagconnect-1.0'
REGIONS = ('T1国内', 'T2内转', '跨楼联程')
SIGNAL_NAMES = ('remaining_slack', 'belt_load', 'transfer_crowd', 'short_tag_share', 'bags_through_gate')
RAW_EXPLAIN_INDEX = (None, None, None, None, None)
RESOURCE = '优先运力车位'
DEFAULT_BUDGET = 14
ACTION = '排优先转运'
MANUAL_ACTION = '核对交接链'
NORMAL_ACTION = '常规中转'
WORKFLOW = '必须保留分拣交接，车位优先留给截关提前量最小的合规行李。'
PLACEMENT_MODE = 'early_run'
POOL_LIMIT = 3
SEPARATE_CONTEXTS = False
HAS_WORKBENCH = True
SAMPLE_NAME = 'bagconnect_register.csv'

FIELDS = (
    Field('slack', '距截关', '分钟', 15, 102, False),
    Field('distance', '转送距离', '百米', 2, 42, False),
    Field('bags', '同批转运行李', '件', 1, 24, True),
    Field('belt', '皮带占用', '%', 14, 98, False),
    Field('priority', '短接标签比例', '%', 0, 100, False),
    Field('transfer', '已用中转', '分钟', 0, 54, False),
)
