{% extends "base.html" %}
{% block title %}{{ ev.title }} — 活动广场{% endblock %}
{% block content %}

<a href="/" class="btn btn-sm" style="margin-bottom:14px;">← 返回</a>

{% if ev.img %}
  <img src="/static/uploads/{{ ev.img }}" class="event-img" alt="{{ ev.title }}" style="border-radius:12px;margin-bottom:16px;"/>
{% endif %}

<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px;">
  <h1 style="font-size:20px;font-weight:500;line-height:1.4;">{{ ev.title }}</h1>
  <span class="tag">{{ ev.category }}</span>
</div>

<div style="font-size:14px;color:#888;margin-bottom:4px;">🕐 {{ ev.date }} {{ ev.time }}</div>
<div style="font-size:14px;color:#888;margin-bottom:14px;">📍 {{ ev.location }}</div>

{% if ev.lat %}
<div id="map" class="map-box" style="margin-bottom:16px;"></div>
{% endif %}

<hr class="divider"/>
<p style="font-size:14px;line-height:1.8;color:#555;margin-bottom:16px;">{{ ev.description }}</p>
<hr class="divider"/>

<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;font-size:14px;">
  <span class="avatar">{{ ev.host_name[0] }}</span>
  <span style="color:#888;">发起人</span> <strong style="font-weight:500;">{{ ev.host_name }}</strong>
</div>

<div style="background:#f5f5f3;border-radius:10px;padding:14px;margin-bottom:16px;font-size:13px;">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
    <span style="color:#888;">已报名</span>
    <span style="font-weight:500;">{{ attendees|length }} / {{ ev.max_attendees }}</span>
  </div>
  <div class="progress-bar">
    <div class="progress-fill" style="width:{{ [((attendees|length) / ev.max_attendees * 100)|int, 100]|min }}%;"></div>
  </div>
  {% if attendees %}
    <div style="margin-top:10px;color:#888;">
      {{ attendees[:5]|map(attribute='name')|join('、') }}{% if attendees|length > 5 %} 等 {{ attendees|length }} 人{% endif %}
    </div>
  {% endif %}
</div>

{% if user and user.id == ev.host_id %}
  <p style="text-align:center;font-size:13px;color:#aaa;margin-bottom:10px;">你是本活动的发起人</p>
  <form method="post" action="/event/{{ ev.id }}/delete" onsubmit="return confirm('确定删除这个活动吗？')">
    <button class="btn btn-danger" style="width:100%;" type="submit">🗑 删除活动</button>
  </form>
{% elif not user %}
  <a href="/login" class="btn btn-primary" style="width:100%;justify-content:center;">登录后报名参加</a>
{% elif attendees|length >= ev.max_attendees and not joined %}
  <button class="btn" style="width:100%;" disabled>名额已满</button>
{% elif joined %}
  <button class="btn" style="width:100%;justify-content:center;" id="cancel-btn">取消报名</button>
{% else %}
  {% set left = ev.max_attendees - attendees|length %}
  <button class="btn btn-primary" style="width:100%;justify-content:center;" id="join-btn">
    免费报名 · 还剩 {{ left }} 个名额
  </button>
{% endif %}

{% endblock %}

{% block scripts %}
{% if ev.lat %}
<script>
  const map = L.map('map', {zoomControl:true, attributionControl:false}).setView([{{ ev.lat }}, {{ ev.lng }}], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
  L.marker([{{ ev.lat }}, {{ ev.lng }}]).addTo(map).bindPopup('{{ ev.location }}').openPopup();
</script>
{% endif %}
<script>
  const joinBtn = document.getElementById('join-btn');
  const cancelBtn = document.getElementById('cancel-btn');
  async function post(url) {
    const r = await fetch(url, {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}});
    return r.json();
  }
  if (joinBtn) joinBtn.addEventListener('click', async () => {
    joinBtn.disabled = true;
    const d = await post('/event/{{ ev.id }}/join');
    alert(d.msg);
    if (d.ok) location.reload();
    else joinBtn.disabled = false;
  });
  if (cancelBtn) cancelBtn.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    const d = await post('/event/{{ ev.id }}/cancel');
    alert(d.msg);
    if (d.ok) location.reload();
    else cancelBtn.disabled = false;
  });
</script>
{% endblock %}
