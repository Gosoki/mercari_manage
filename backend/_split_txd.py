# -*- coding: utf-8 -*-
import ast, os
from collections import defaultdict

ROOT = 'src/use_mercari/get_to_du_list'
SRCFILE = f'{ROOT}/transaction_detail.py'
src = open(SRCFILE, encoding='utf-8').read()
lines = src.split('\n')
tree = ast.parse(src)

target = {
 '_WAIT_SHIPPING_KINDS':'_common','_WAIT_SHIPPING_TITLE':'_common','_WAIT_REPLY_KINDS':'_common',
 '_is_wait_shipping_todo':'_common','_compose_sender_address':'_common','_parse_shipping_info':'_common',
 '_parse_messages':'_common','_format_ts':'_common',
 '_WAIT_TIMEOUT_SEC':'_captures','_RELOAD_INTERVAL_SEC':'_captures','_AFTER_FIRST_GRACE_SEC':'_captures','_wait_for_both_captures':'_captures',
 '_persist_transaction_detail':'_cache','_persist_qr_image_path':'_cache','_clear_qr_image':'_cache','get_cached_transaction_detail':'_cache','list_uncached_detail_todo_ids':'_cache',
 '_QR_CODE_IMG_SELECTOR':'_qr_facility','_qr_code_exists':'_qr_facility','_save_qr_code_image':'_qr_facility','_SHIPPING_FACILITY_JS':'_qr_facility','_extract_shipping_facility':'_qr_facility','_persist_shipping_facility':'_qr_facility',
 '_click_visible_button_by_text':'_ui',
 'fetch_transaction_detail':'detail',
 '_REVIEW_TEXTAREA_PLACEHOLDER':'review','_REVIEW_SUBMIT_BUTTON_TEXT':'review','_REVIEW_CONFIRM_BUTTON_TEXT':'review','_REVIEW_COMPLETED_TEXT':'review','submit_transaction_review':'review',
 '_REPLY_TEXTAREA_PLACEHOLDERS':'wait_reply.message','_REPLY_SEND_BUTTON_TEXT':'wait_reply.message','send_transaction_message':'wait_reply.message',
 'SUPPORTED_REACTIONS':'wait_reply.reaction','send_message_reaction_by_index':'wait_reply.reaction',
 '_SIZE_SELECT_BUTTON_TEXT':'wait_shipping.shipping_select','_SELECT_NEXT_BUTTON_TEXT':'wait_shipping.shipping_select','_SELECT_FINISH_BUTTON_TEXT':'wait_shipping.shipping_select','_GENERATE_SHIP_CODE_TEXTS':'wait_shipping.shipping_select','_FACILITY_XPATHS':'wait_shipping.shipping_select','_FACILITY_ARIA_LABELS':'wait_shipping.shipping_select','start_select_shipping_class':'wait_shipping.shipping_select','_click_generate_ship_code':'wait_shipping.shipping_select','confirm_shipping_selection':'wait_shipping.shipping_select',
 '_SCAN_QR_BUTTON_TEXT':'wait_shipping.qr_scan',
 '_SCAN_START_BUTTON_TEXT':'wait_shipping.qr_scan','_SCAN_OK_TEXT':'wait_shipping.qr_scan','_FAKE_CAMERA_JS':'wait_shipping.qr_scan','_click_scan_qr_and_open_scanner':'wait_shipping.qr_scan','push_remote_camera_frame':'wait_shipping.qr_scan','capture_qr_scanner_frame':'wait_shipping.qr_scan',
 '_SHIP_CONFIRM_CHECKBOX_TEXTS':'wait_shipping.ship_finalize','_NOTIFY_SHIP_BUTTON_TEXT':'wait_shipping.ship_finalize','_SHIPPED_CONFIRM_BUTTON_TEXT':'wait_shipping.ship_finalize','_SHIP_SUCCESS_TEXT':'wait_shipping.ship_finalize','read_post_shipping_confirm_info':'wait_shipping.ship_finalize','_tick_ship_confirm_checkboxes':'wait_shipping.ship_finalize','_has_tracking_number':'wait_shipping.ship_finalize','finalize_post_shipping':'wait_shipping.ship_finalize',
 '_CHANGE_METHOD_BUTTON_TEXT':'wait_shipping.change_method','_CHANGE_METHOD_RADIO_NAME':'wait_shipping.change_method','_CHANGE_METHOD_SUBMIT_TEXT':'wait_shipping.change_method','_REVISE_SLIP_BUTTON_TEXT':'wait_shipping.change_method','_REVISE_SLIP_BUTTON_LOCATION':'wait_shipping.change_method','_click_change_method_entry':'wait_shipping.change_method','click_change_shipping_method':'wait_shipping.change_method','_click_dialog_change_confirm':'wait_shipping.change_method','revise_shipping_after_qr':'wait_shipping.change_method','_scrape_shipping_method_options':'wait_shipping.change_method','confirm_change_shipping_method':'wait_shipping.change_method',
}

def node_name(n):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): return n.name
    if isinstance(n,ast.Assign):
        for t in n.targets:
            if isinstance(t,ast.Name): return t.id
    if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name): return n.target.id
    return None

cat=[]
for n in tree.body:
    nm=node_name(n)
    if nm in target:
        s=n.lineno
        if getattr(n,'decorator_list',None):
            s=min(s,min(d.lineno for d in n.decorator_list))
        cat.append([s,n.end_lineno,nm,target[nm]])

owned=set()
for s,e,nm,mod in cat:
    for L in range(s,e+1): owned.add(L)

def cb(L):
    t=lines[L-1].strip()
    return t=='' or t.startswith('#')

for c in cat:
    L=c[0]-1
    while L>=1 and (L not in owned) and cb(L):
        L-=1
    c[0]=L+1
cat.sort(key=lambda x:x[0])

STD=("import asyncio\nimport json\nimport logging\nimport re\nimport time\n"
     "from datetime import datetime, timezone\nfrom typing import Any, Dict, List, Optional, Tuple\n")

def ext_block(d):
    s='.'*(3+d); u='.'*(2+d)
    return (
     f"from {s}db_manage.database import DatabaseManager\n"
     f"from {s}db_manage.models.todo_item import TodoItemModel\n"
     f"from {s}use_web.image_storage import save_image_bytes\n"
     f"from {s}ssl_mitm_proxy.capture_config import (\n"
     "    clear_shipping_info_response_file,\n"
     "    clear_transaction_messages_response_file,\n"
     "    read_shipping_info_response,\n"
     "    read_transaction_messages_response,\n)\n"
     f"from {s}web_drive.core.manager import EdgeWebDriveManager, get_web_drive_manager\n"
     f"from {s}web_drive.core.mitm_session import (\n"
     "    _raise_login_required_for,\n"
     "    login_redirect_state_for,\n"
     "    mitm_automation_browser,\n)\n"
     f"from {s}web_drive.core.paths import mercari_account_key, mercari_id_from_account_key\n"
     f"from {u}get_order.get_in_progress_order.get_order_info import apply_item_info_to_order\n"
     f"from {u}sync_progress import make_sync_reporter\n"
    )

sib={
 '_common':[], '_captures':[], '_ui':[],
 '_cache':[('._common',['_WAIT_REPLY_KINDS','_WAIT_SHIPPING_KINDS','_WAIT_SHIPPING_TITLE'])],
 '_qr_facility':[('._cache',['_persist_qr_image_path'])],
 'detail':[('._cache',['_clear_qr_image','_persist_transaction_detail']),('._captures',['_wait_for_both_captures']),('._common',['_WAIT_REPLY_KINDS','_is_wait_shipping_todo','_parse_messages','_parse_shipping_info']),('._qr_facility',['_extract_shipping_facility','_qr_code_exists','_save_qr_code_image'])],
 'review':[],
 'wait_reply.message':[], 'wait_reply.reaction':[],
 'wait_shipping.qr_scan':[],
 'wait_shipping.shipping_select':[('.._common',['_is_wait_shipping_todo']),('.._qr_facility',['_extract_shipping_facility','_persist_shipping_facility','_save_qr_code_image']),('.qr_scan',['_click_scan_qr_and_open_scanner'])],
 'wait_shipping.ship_finalize':[('.._common',['_is_wait_shipping_todo']),('.._ui',['_click_visible_button_by_text']),('.qr_scan',['_SCAN_OK_TEXT'])],
 'wait_shipping.change_method':[('.._cache',['_clear_qr_image']),('.._common',['_is_wait_shipping_todo'])],
}

modpath={
 '_common':(f'{ROOT}/transaction_detail/_common.py',1,'shared: todo kind judgment + shipping/messages parsing + ts format'),
 '_captures':(f'{ROOT}/transaction_detail/_captures.py',1,'shared: MITM dual-API capture wait loop'),
 '_ui':(f'{ROOT}/transaction_detail/_ui.py',1,'shared: click visible button by text helper'),
 '_cache':(f'{ROOT}/transaction_detail/_cache.py',1,'shared: detail cache read/write + uncached enumeration + qr path persist'),
 '_qr_facility':(f'{ROOT}/transaction_detail/_qr_facility.py',1,'shared: ship-code image grab/save + shipping-facility extraction'),
 'detail':(f'{ROOT}/transaction_detail/detail.py',1,'fetch_transaction_detail main flow (shared by wait-shipping/wait-reply + precache)'),
 'review':(f'{ROOT}/transaction_detail/review.py',1,'review (ReviewedSeller): submit transaction review'),
 'wait_reply.message':(f'{ROOT}/transaction_detail/wait_reply/message.py',2,'wait-reply: send transaction message'),
 'wait_reply.reaction':(f'{ROOT}/transaction_detail/wait_reply/reaction.py',2,'wait-reply: send emoji reaction to buyer message'),
 'wait_shipping.qr_scan':(f'{ROOT}/transaction_detail/wait_shipping/qr_scan.py',2,'wait-shipping: QR scan entry + remote camera inject/push'),
 'wait_shipping.shipping_select':(f'{ROOT}/transaction_detail/wait_shipping/shipping_select.py',2,'wait-shipping: pick item size & facility + issue ship code'),
 'wait_shipping.ship_finalize':(f'{ROOT}/transaction_detail/wait_shipping/ship_finalize.py',2,'wait-shipping: post-ship confirm + finalize'),
 'wait_shipping.change_method':(f'{ROOT}/transaction_detail/wait_shipping/change_method.py',2,'wait-shipping: change shipping method / revise after code'),
}

bodies=defaultdict(list)
for s,e,nm,mod in cat:
    bodies[mod].append((s,'\n'.join(lines[s-1:e])))

written=[]
for mod,(path,depth,doc) in modpath.items():
    os.makedirs(os.path.dirname(path),exist_ok=True)
    header=[]
    header.append('# -*- coding: utf-8 -*-')
    header.append(f'"""{doc}"""')
    header.append('from __future__ import annotations')
    header.append('')
    header.append(STD.rstrip('\n'))
    extra=''
    for rel,names in sib[mod]:
        extra+=f"from {rel} import {', '.join(sorted(names))}\n"
    header.append(ext_block(depth).rstrip('\n'))
    if extra:
        header.append(extra.rstrip('\n'))
    header.append('')
    header.append('log = logging.getLogger(__name__)')
    body=[c for _,c in sorted(bodies[mod],key=lambda x:x[0])]
    bodytext='\n\n'.join(b.strip('\n') for b in body)
    content='\n'.join(header)+'\n\n\n'+bodytext+'\n'
    open(path,'w',encoding='utf-8').write(content)
    written.append((path,content.count('\n')+1))

for sub,doc in [('wait_shipping','wait-shipping processing sub-package'),('wait_reply','wait-reply processing sub-package')]:
    ip=f'{ROOT}/transaction_detail/{sub}/__init__.py'
    open(ip,'w',encoding='utf-8').write(f'# -*- coding: utf-8 -*-\n"""{doc}"""\n')
    written.append((ip,2))

for p,n in written: print(f'{n:>5}  {p}')
print('TOTAL files:',len(written))
