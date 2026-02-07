import streamlit as st
import datetime
import json
import time
from supabase import create_client, Client

# ==========================================
# 1. 基础配置 & 云数据库自动连接
# ==========================================
st.set_page_config(page_title="SkillBridge Cloud", layout="wide", page_icon="☁️")

# ⚠️⚠️⚠️ 请重新填入你的 Supabase 信息 ⚠️⚠️⚠️
SUPABASE_URL = "https://wioryevmdrsqqhgzwgui.supabase.co"
SUPABASE_KEY = "sb_secret_9mNJ47OP0ix0Lz8voyh8Ww_qTCroPfe"

# [逻辑变更] 这里的连接是自动执行的，没有按钮触发
@st.cache_resource
def init_connection():
    try:
        if "你的" in SUPABASE_URL: return None # 防止没填Key报错
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        return None

supabase = init_connection()

# CSS 样式 (保持不变)
st.markdown("""
<style>
    .main { background-color: #f8f9fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    .chat-container { height: 400px; overflow-y: scroll; padding: 20px; background-color: #fff; border: 1px solid #eee; border-radius: 10px;}
    .chat-bubble { padding: 8px 12px; border-radius: 15px; margin-bottom: 8px; max-width: 70%; display: block; clear: both; font-size: 14px; }
    .chat-me { background-color: #95ec69; color: black; float: right; }
    .chat-other { background-color: #f1f1f1; color: #333; float: left; }
    .stButton>button { border-radius: 20px; width: 100%; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    .status-doing { background-color: #e6f7ff; color: #1890ff; }
    .status-wait { background-color: #fff7e6; color: #fa8c16; }
    .status-done { background-color: #f6ffed; color: #52c41a; }
    .deal-box { background-color: #fffbe6; border: 1px solid #ffe58f; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
    .deal-box-disabled { background-color: #f5f5f5; border: 1px solid #ddd; padding: 15px; border-radius: 8px; margin-bottom: 15px; color: #999; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据层
# ==========================================

def load_data():
    if not supabase: return {} 
    try:
        # 直接读取，用户无感知
        response = supabase.table("app_storage").select("data").eq("id", 1).execute()
        if response.data:
            return response.data[0]['data']
        else:
            return {}
    except Exception as e:
        st.error(f"云端连接异常: {e}")
        return {"users": {}, "demands": [], "services": [], "orders": [], "chat_rooms": {}, "unread": {}, "chat_contexts": {}}

def save_data(data):
    if not supabase: return
    try:
        supabase.table("app_storage").update({"data": data}).eq("id", 1).execute()
    except Exception as e:
        st.error(f"保存失败: {e}")

# 辅助函数
def get_room_id(user1, user2):
    return "_".join(sorted([user1, user2]))

def add_unread(db_data, to_user, from_user):
    if to_user not in db_data['unread']: db_data['unread'][to_user] = {}
    if from_user not in db_data['unread'][to_user]: db_data['unread'][to_user][from_user] = 0
    db_data['unread'][to_user][from_user] += 1

def clear_unread(db_data, owner, target_contact):
    if owner in db_data['unread'] and target_contact in db_data['unread'][owner]:
        if db_data['unread'][owner][target_contact] > 0:
            db_data['unread'][owner][target_contact] = 0
            save_data(db_data)

def get_total_unread(owner):
    db_data = load_data()
    if owner not in db_data['unread']: return 0
    return sum(db_data['unread'][owner].values())

# ==========================================
# 3. 实时片段 (Fragments)
# ==========================================

@st.fragment(run_every=2)
def render_sidebar_fragment(current_user):
    st.write(f"👋 **{current_user}**")
    total = get_total_unread(current_user)
    msg_label = f"💬 消息中心"
    if total > 0: msg_label += f" 🔴({total})"
    
    if st.button("🏠 交易大厅", key="nav_m"): st.session_state.page = "marketplace"; st.rerun()
    if st.button(msg_label, key="nav_c"): st.session_state.page = "chat"; st.rerun()
    if st.button("📦 我的订单", key="nav_o"): st.session_state.page = "orders"; st.rerun()
    st.divider()
    if st.button("退出", key="nav_l"): st.session_state.user = None; st.rerun()

@st.fragment(run_every=3)
def render_contact_list(current_user, current_target):
    st.write("对话列表")
    fresh_db = load_data()
    my_unread = fresh_db['unread'].get(current_user, {})
    for room_id in fresh_db['chat_rooms']:
        if current_user in room_id:
            parts = room_id.split('_')
            other = parts[0] if parts[1] == current_user else parts[1]
            count = my_unread.get(other, 0)
            btn_label = f"👤 {other}"
            if count > 0: btn_label += f" 🔴 {count}"
            b_type = "primary" if current_target == other else "secondary"
            if st.button(btn_label, key=f"contact_{room_id}", type=b_type):
                st.session_state.current_chat_target = other
                st.rerun()

@st.fragment(run_every=2)
def render_chat_window(current_user, target_user):
    fresh_db = load_data()
    room_id = get_room_id(current_user, target_user)
    
    # 自动消红点
    if current_user in fresh_db['unread'] and fresh_db['unread'][current_user].get(target_user, 0) > 0:
        clear_unread(fresh_db, current_user, target_user)
    
    # 上下文展示
    ctx = fresh_db['chat_contexts'].get(room_id)
    if ctx and ctx['data']['user'] == target_user:
        item_id = ctx['data']['id']
        item_type = ctx['type']
        is_active = False
        if item_type == 'demand': is_active = any(d['id'] == item_id for d in fresh_db['demands'])
        elif item_type == 'service': is_active = any(s['id'] == item_id for s in fresh_db['services'])
            
        if is_active:
            st.markdown(f"<div class='deal-box'>🔗 关联项目：**{ctx['data']['title']}**", unsafe_allow_html=True)
            if item_type == 'demand':
                st.caption(f"预算: {ctx['data']['budget']}")
                if st.button("⚡ 立即接单 (我是执行方)", key="btn_accept"):
                    new_order = {"id": int(datetime.datetime.now().timestamp()), "buyer": target_user, "seller": current_user, "title": ctx['data']['title'], "price": ctx['data']['budget'], "status": "进行中", "time": str(datetime.datetime.now().strftime("%Y-%m-%d"))}
                    fresh_db['orders'].append(new_order)
                    fresh_db['demands'] = [d for d in fresh_db['demands'] if d['id'] != item_id]
                    fresh_db['chat_rooms'][room_id].append({"sender": "System", "text": "✅ 接单成功", "time": str(datetime.datetime.now())})
                    add_unread(fresh_db, target_user, current_user)
                    save_data(fresh_db)
                    st.success("接单成功")
            else:
                st.caption(f"报价: {ctx['data']['price']}")
                if st.button("🤝 立即雇佣 (我是需求方)", key="btn_hire"):
                    new_order = {"id": int(datetime.datetime.now().timestamp()), "buyer": current_user, "seller": target_user, "title": ctx['data']['title'], "price": ctx['data']['price'], "status": "进行中", "time": str(datetime.datetime.now().strftime("%Y-%m-%d"))}
                    fresh_db['orders'].append(new_order)
                    fresh_db['chat_rooms'][room_id].append({"sender": "System", "text": "✅ 雇佣成功", "time": str(datetime.datetime.now())})
                    add_unread(fresh_db, target_user, current_user)
                    save_data(fresh_db)
                    st.success("雇佣成功")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='deal-box-disabled'>🔒 关联项目：**{ctx['data']['title']}**<br><small>(该订单已售出或已下架)</small></div>", unsafe_allow_html=True)

    # 聊天记录
    history = fresh_db['chat_rooms'].get(room_id, [])
    chat_html = '<div class="chat-container">'
    for msg in history:
        is_me = (msg['sender'] == current_user)
        cls = "chat-me" if is_me else "chat-other"
        chat_html += f'<div class="chat-bubble {cls}"><b>{msg["sender"]}:</b> {msg["text"]}</div>'
    chat_html += '</div>'
    st.markdown(chat_html, unsafe_allow_html=True)

@st.fragment(run_every=3)
def render_marketplace_lists(current_user):
    fresh_db = load_data()
    tab1, tab2 = st.tabs(["📋 需求广场", "🌟 技能市场"])
    
    def go_chat_persistent(target_user, item_data, item_type):
        st.session_state.page = "chat"
        st.session_state.current_chat_target = target_user
        room_id = get_room_id(current_user, target_user)
        if room_id not in fresh_db['chat_contexts']: fresh_db['chat_contexts'][room_id] = {}
        fresh_db['chat_contexts'][room_id] = {"type": item_type, "data": item_data}
        if room_id not in fresh_db['chat_rooms']: fresh_db['chat_rooms'][room_id] = []
        save_data(fresh_db)
        st.rerun()

    def delete_item(list_key, item_id):
        fresh_db[list_key] = [i for i in fresh_db[list_key] if i['id'] != item_id]
        save_data(fresh_db)
        st.toast("已下架")
        st.rerun()

    with tab1:
        if not fresh_db['demands']: st.info("暂无需求")
        for item in reversed(fresh_db['demands']):
            is_mine = item['user'] == current_user
            c = st.columns([4, 1] if not is_mine else [4, 1])
            with c[0]: st.info(f"【需求】**{item['title']}** | 💰{item['budget']} | 👤{item['user']}")
            with c[1]:
                if not is_mine:
                    if st.button("接单", key=f"d_{item['id']}"): go_chat_persistent(item['user'], item, 'demand')
                else:
                    if st.button("🗑️ 下架", key=f"del_d_{item['id']}"): delete_item('demands', item['id'])
    
    with tab2:
        if not fresh_db['services']: st.info("暂无技能")
        for item in reversed(fresh_db['services']):
            is_mine = item['user'] == current_user
            c = st.columns([4, 1] if not is_mine else [4, 1])
            with c[0]: st.success(f"【技能】**{item['title']}** | 💵{item['price']} | 👤{item['user']}")
            with c[1]:
                if not is_mine:
                    if st.button("雇佣", key=f"s_{item['id']}"): go_chat_persistent(item['user'], item, 'service')
                else:
                    if st.button("🗑️ 下架", key=f"del_s_{item['id']}"): delete_item('services', item['id'])

@st.fragment(run_every=3)
def render_orders_list(current_user):
    fresh_db = load_data()
    my_buy_orders = [o for o in fresh_db['orders'] if o['buyer'] == current_user]
    my_sell_orders = [o for o in fresh_db['orders'] if o['seller'] == current_user]
    tab1, tab2 = st.tabs([f"我买入的", f"我卖出的"])
    
    def render_order_card(order, role):
        status_map = {"进行中": ("status-doing", "info"), "待验收": ("status-wait", "warning"), "已完成": ("status-done", "success")}
        css, _ = status_map.get(order['status'], ("status-doing", "info"))
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{order['title']}**")
                st.caption(f"💰 {order['price']} | {order['status']}")
                st.markdown(f"<span class='status-badge {css}'>{order['status']}</span>", unsafe_allow_html=True)
            with c2:
                if role == "seller" and order['status'] == "进行中":
                    if st.button("交付", key=f"dlv_{order['id']}"):
                        for o in fresh_db['orders']:
                            if o['id'] == order['id']: o['status'] = "待验收"
                        room_id = get_room_id(order['buyer'], order['seller'])
                        fresh_db['chat_rooms'][room_id].append({"sender": "System", "text": f"🔔 交付通知：【{order['title']}】已交付", "time": str(datetime.datetime.now())})
                        add_unread(fresh_db, order['buyer'], order['seller'])
                        save_data(fresh_db)
                        st.rerun()
                elif role == "buyer" and order['status'] == "待验收":
                    if st.button("验收", key=f"cfm_{order['id']}"):
                        for o in fresh_db['orders']:
                            if o['id'] == order['id']: o['status'] = "已完成"
                        room_id = get_room_id(order['buyer'], order['seller'])
                        fresh_db['chat_rooms'][room_id].append({"sender": "System", "text": f"💰 验收通知：【{order['title']}】已完成", "time": str(datetime.datetime.now())})
                        add_unread(fresh_db, order['seller'], order['buyer'])
                        save_data(fresh_db)
                        st.rerun()

    with tab1:
        for order in reversed(my_buy_orders): render_order_card(order, "buyer")
    with tab2:
        for order in reversed(my_sell_orders): render_order_card(order, "seller")

# ==========================================
# 4. 主程序
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "login"
if 'current_chat_target' not in st.session_state: st.session_state.current_chat_target = None

# --- 登录 ---
if st.session_state.user is None:
    st.title("SkillBridge 登录 (Cloud)")
    
    col1, col2 = st.columns(2)
    with col1:
        u = st.text_input("用户名")
        p = st.text_input("密码", type="password")
        if st.button("登录"):
            # 自动连接获取数据
            current_db = load_data()
            if u in current_db['users'] and current_db['users'][u] == p:
                st.session_state.user = u
                st.session_state.page = "marketplace"
                st.rerun()
            else: st.error("账号密码错误或数据库未连接")
    with col2:
        if st.button("注册"):
            current_db = load_data()
            if u and p:
                current_db['users'][u] = p
                save_data(current_db)
                st.success("注册成功")

# --- 登录后 ---
else:
    with st.sidebar:
        render_sidebar_fragment(st.session_state.user)

    if st.session_state.page == "marketplace":
        st.subheader("交易大厅")
        c1, c2 = st.columns([3, 1])
        with c1: render_marketplace_lists(st.session_state.user)
        with c2:
            st.write("#### 🚀 快速发布")
            with st.form("quick_pub"):
                type_ = st.selectbox("类型", ["需求", "技能"])
                title = st.text_input("标题")
                price = st.text_input("价格/预算")
                if st.form_submit_button("发布"):
                    current_db = load_data()
                    new_item = {
                        "id": int(datetime.datetime.now().timestamp()),
                        "user": st.session_state.user, "title": title
                    }
                    if type_ == "需求":
                        new_item["budget"] = price
                        current_db['demands'].append(new_item)
                    else:
                        new_item["price"] = price
                        current_db['services'].append(new_item)
                    save_data(current_db)
                    st.toast("发布成功")

    elif st.session_state.page == "chat":
        st.subheader("消息中心")
        c1, c2 = st.columns([1, 3])
        with c1: render_contact_list(st.session_state.user, st.session_state.current_chat_target)
        with c2:
            target = st.session_state.current_chat_target
            if target:
                st.write(f"与 **{target}** 对话")
                render_chat_window(st.session_state.user, target)
                
                with st.form("msg_form", clear_on_submit=True):
                    txt = st.text_input("输入...", label_visibility="collapsed")
                    if st.form_submit_button("发送"):
                        fresh_db = load_data()
                        room_id = get_room_id(st.session_state.user, target)
                        if room_id not in fresh_db['chat_rooms']: fresh_db['chat_rooms'][room_id] = []
                        fresh_db['chat_rooms'][room_id].append({"sender": st.session_state.user, "text": txt, "time": str(datetime.datetime.now())})
                        add_unread(fresh_db, target, st.session_state.user)
                        save_data(fresh_db)
            else:
                st.info("👈 请选择联系人")

    elif st.session_state.page == "orders":
        st.subheader("📦 我的订单")
        render_orders_list(st.session_state.user)