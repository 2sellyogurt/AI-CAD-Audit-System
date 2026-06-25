// API Config Page JavaScript
function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showToast(msg, type) {
  var t = document.getElementById('apic-toast');
  t.textContent = msg;
  t.className = 'apic-toast ' + type;
  setTimeout(function() { t.className = 'apic-toast'; }, 3000);
}

function showResult(purpose, msg, ok) {
  var r = document.getElementById(purpose + '-result');
  r.textContent = msg;
  r.className = 'apic-result ' + (ok ? 'ok' : 'err');
}

function onModelChange(purpose) {
  var sel = document.getElementById(purpose + '-model');
  var opt = sel.selectedOptions[0];
  var infoDiv = document.getElementById(purpose + '-model-info');
  var customModel = document.getElementById(purpose + '-custom-model');
  var customUrl = document.getElementById(purpose + '-custom-url');
  var noteDiv = document.getElementById(purpose + '-note');

  if (sel.value === 'custom') {
    customModel.style.display = 'block';
    customUrl.style.display = 'block';
    infoDiv.style.display = 'none';
    return;
  }

  customModel.style.display = 'none';
  customUrl.style.display = 'none';

  if (opt && opt.dataset.url) {
    var html = '<table>' +
      '<tr><td>厂商</td><td>' + _esc(opt.parentNode.label) + '</td></tr>' +
      '<tr><td>价格</td><td>' + _esc(opt.dataset.price || '') + '</td></tr>' +
      '<tr><td>上下文</td><td>' + _esc(opt.dataset.context || '') + '</td></tr>' +
      '<tr><td>限流</td><td>' + _esc(opt.dataset.rpm || '') + ' RPM / ' + _esc(opt.dataset.concurrent || '') + ' 并发</td></tr>' +
      '</table>';
    infoDiv.innerHTML = html;
    infoDiv.style.display = 'block';
  } else {
    infoDiv.style.display = 'none';
  }

  // DeepSeek 视觉提示
  if (purpose === 'vision' && opt && opt.dataset.provider === 'deepseek') {
    noteDiv.textContent = '⚠ DeepSeek 暂不支持视觉模型，请选择其他厂商';
  } else if (opt && opt.dataset.provider === 'doubao') {
    noteDiv.innerHTML = '<div style="background:#fff7e6;border:1px solid #ffd591;border-radius:6px;padding:10px;margin-top:8px">' +
      '<div style="font-weight:600;color:#d46b08;margin-bottom:6px">⚠ 豆包必须使用 Endpoint ID</div>' +
      '<div style="line-height:1.8">' +
      '1. 登录 <a href="https://console.volcengine.com/ark" target="_blank" style="color:#1677ff">火山方舟控制台</a><br>' +
      '2. 左侧菜单选择「在线推理」→「推理接入点」<br>' +
      '3. 点击「创建接入点」，选择模型（如 Doubao-Seed-1.6）<br>' +
      '4. 创建完成后，复制接入点 ID（格式如 ep-20250101-xxxx）<br>' +
      '5. 在下方「自定义模型名称」字段填入 Endpoint ID<br>' +
      '6. 从「API Key 管理」创建 Key 并填入上方' +
      '</div></div>';
    // 豆包强制显示自定义模型输入框
    customModel.style.display = 'block';
    document.getElementById(purpose + '-custom-name').placeholder = '粘贴 Endpoint ID（如 ep-20250101-xxxx）';
  } else {
    noteDiv.textContent = '';
  }
}

function getModelData(purpose) {
  var sel = document.getElementById(purpose + '-model');
  var opt = sel.selectedOptions[0];

  if (sel.value === 'custom') {
    return {
      model: document.getElementById(purpose + '-custom-name').value.trim(),
      provider: 'custom',
      base_url: document.getElementById(purpose + '-custom-url-input').value.trim(),
      api_key: document.getElementById(purpose + '-key').value.trim(),
    };
  }

  // 豆包特殊处理：必须使用自定义Endpoint ID
  var provider = opt ? opt.dataset.provider : '';
  var modelName = sel.value;
  if (provider === 'doubao') {
    var customName = document.getElementById(purpose + '-custom-name').value.trim();
    if (customName) {
      modelName = customName;
    }
  }

  return {
    model: modelName,
    provider: provider,
    base_url: opt ? opt.dataset.url : '',
    api_key: document.getElementById(purpose + '-key').value.trim(),
  };
}

async function saveConfig(purpose) {
  var data = getModelData(purpose);

  if (!data.model) { showToast('请选择或填写模型', 'warn'); return; }
  if (!data.base_url) { showToast('请填写 API URL', 'warn'); return; }
  if (!data.api_key) { showToast('请填写 API Key', 'warn'); return; }

  // 豆包必须提供Endpoint ID
  if (data.provider === 'doubao' && !data.model.startsWith('ep-')) {
    showToast('豆包必须填写Endpoint ID（以 ep- 开头）', 'warn');
    document.getElementById(purpose + '-custom-name').focus();
    return;
  }

  try {
    var r = await fetch('/admin/api/api-config/' + purpose, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    var d = await r.json();
    if (d.ok) {
      showToast('保存成功', 'ok');
      showResult(purpose, '✅ 配置已保存', true);
    } else {
      showToast('保存失败: ' + (d.error || ''), 'err');
      showResult(purpose, '❌ ' + (d.error || '保存失败'), false);
    }
  } catch(e) {
    showToast('网络错误: ' + e.message, 'err');
    showResult(purpose, '❌ 网络错误: ' + e.message, false);
  }
}

async function testConfig(purpose) {
  var data = getModelData(purpose);

  if (!data.api_key) { showToast('请先填写 API Key', 'warn'); return; }
  if (!data.model) { showToast('请先选择模型', 'warn'); return; }
  if (!data.base_url) { showToast('请先填写 API URL', 'warn'); return; }

  // 豆包必须提供Endpoint ID
  if (data.provider === 'doubao' && !data.model.startsWith('ep-')) {
    showToast('豆包必须填写Endpoint ID（以 ep- 开头）', 'warn');
    document.getElementById(purpose + '-custom-name').focus();
    return;
  }

  showResult(purpose, '⏳ 正在测试连接...', true);
  try {
    var r = await fetch('/admin/api/api-config/' + purpose + '/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    var d = await r.json();
    if (d.ok) {
      showToast('连接成功', 'ok');
      showResult(purpose, '✅ ' + (d.message || '连接成功'), true);
    } else {
      showToast('连接失败', 'err');
      var troubleshoot = d.troubleshoot || '';
      showResult(purpose, '❌ ' + (d.error || '连接失败') + (troubleshoot ? '\n\n💡 排查建议：\n' + troubleshoot : ''), false);
    }
  } catch(e) {
    showToast('网络错误: ' + e.message, 'err');
    showResult(purpose, '❌ 网络错误: ' + e.message + '\n\n💡 排查建议：\n1. 检查电脑是否已连接互联网\n2. 如果是公司网络，可能需要配置代理\n3. 尝试在浏览器中直接访问 ' + data.base_url + ' 看能否打开\n4. 检查防火墙是否拦截了该地址', false);
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  // 密码框焦点切换
  document.querySelectorAll('input[type=password]').forEach(function(inp) {
    inp.addEventListener('focus', function() { this.type = 'text'; });
    inp.addEventListener('blur', function() { this.type = 'password'; });
  });

  // 绑定按钮事件
  var btnSaveText = document.getElementById('btn-save-text');
  var btnTestText = document.getElementById('btn-test-text');
  var btnSaveVision = document.getElementById('btn-save-vision');
  var btnTestVision = document.getElementById('btn-test-vision');

  if (btnSaveText) btnSaveText.addEventListener('click', function() { saveConfig('text'); });
  if (btnTestText) btnTestText.addEventListener('click', function() { testConfig('text'); });
  if (btnSaveVision) btnSaveVision.addEventListener('click', function() { saveConfig('vision'); });
  if (btnTestVision) btnTestVision.addEventListener('click', function() { testConfig('vision'); });

  // 绑定select change事件
  var textModel = document.getElementById('text-model');
  var visionModel = document.getElementById('vision-model');
  if (textModel) textModel.addEventListener('change', function() { onModelChange('text'); });
  if (visionModel) visionModel.addEventListener('change', function() { onModelChange('vision'); });

  // 初始化显示模型信息
  ['text', 'vision'].forEach(function(p) {
    var sel = document.getElementById(p + '-model');
    if (sel && sel.value && sel.value !== 'custom') {
      onModelChange(p);
    }
  });
});
