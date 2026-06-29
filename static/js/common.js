/* =====================================================
   common.js
   全ページ共通スクリプト
   ===================================================== */

/* ── ハンバーガーメニュー開閉 ── */
function toggleNav() {
  const nav = document.getElementById('globalNav');
  if (nav) nav.classList.toggle('nav-open');
}

/* ── 管理メニュードロップダウン開閉 ── */
function toggleAdminMenu(e) {
  e.stopPropagation();
  const dropdown = document.getElementById('adminMenuDropdown');
  const arrow = e.currentTarget.querySelector('.admin-menu-arrow');
  if (dropdown) dropdown.classList.toggle('open');
  if (arrow) arrow.classList.toggle('expanded');
}

document.addEventListener('click', function (e) {
  if (!e.target.closest('.nav-toggle') && !e.target.closest('#globalNav')) {
    const nav = document.getElementById('globalNav');
    if (nav) nav.classList.remove('nav-open');
  }
  if (!e.target.closest('.admin-menu-wrapper')) {
    const dropdown = document.getElementById('adminMenuDropdown');
    if (dropdown) dropdown.classList.remove('open');
    const arrow = document.querySelector('.admin-menu-arrow');
    if (arrow) arrow.classList.remove('expanded');
  }
});

/* ── トースト自動非表示 ── */
document.addEventListener("DOMContentLoaded", function () {
  // querySelectorAll で複数トーストすべてに適用（Django messages 複数表示対応）
  document.querySelectorAll(".toast.show").forEach(function (toast) {
    toast.addEventListener("click", function () {
      toast.classList.add("hide");
      setTimeout(function () { toast.remove(); }, 500);
    });

    setTimeout(function () {
      toast.classList.add("hide");
      setTimeout(function () { toast.remove(); }, 500);
    }, 3000);
  });
});

/* ── カスタム確認ダイアログ（window.confirm の代替） ──
   iOS Safari では window.confirm() がブロック・無視されることがあるため、
   モーダル形式のカスタムダイアログを使用する。
   ─────────────────────────────────────────────────── */

/**
 * カスタム確認ダイアログを表示する
 * @param {string}   message                      - ダイアログに表示するメッセージ
 * @param {Function} onOk                         - OK ボタン押下時に呼ばれるコールバック
 * @param {Function} [onCancel]                   - キャンセル時に呼ばれるコールバック（省略可）
 * @param {string}   [okLabel='確認']             - OK ボタンのラベル（省略可）
 * @param {string}   [okClass='btn-danger']       - OK ボタンの CSS クラス（省略可）
 * @param {string}   [cancelLabel='キャンセル']   - 戻るボタンのラベル（省略可）
 * @param {string}   [title]                      - ダイアログのタイトル（省略可）
 */
function showConfirm(message, onOk, onCancel, okLabel, okClass, cancelLabel, title) {
  const btnLabel    = okLabel     || '確認';
  const btnClass    = okClass     || 'btn-danger';
  const cancelText  = cancelLabel || 'キャンセル';
  const titleHtml   = title
    ? "<div style='font-size:16px;font-weight:bold;margin:0 0 12px;color:#1a1a2e;'>" + title + "</div>"
    : "";
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay open';
  overlay.style.zIndex = '9999';
  overlay.innerHTML =
    "<div class='modal-box' style='max-width:420px;padding:28px 32px;'>" +
      titleHtml +
      "<p style='margin:0 0 20px;font-size:15px;line-height:1.6;color:#333;'>" +
        message.replace(/\n/g, '<br>') +
      "</p>" +
      "<div class='modal-footer'>" +
        "<button id='_cfm_cancel' class='btn btn-light btn-md'>" + cancelText + "</button>" +
        "<button id='_cfm_ok'     class='btn " + btnClass + " btn-md'>" + btnLabel + "</button>" +
      "</div>" +
    "</div>";

  document.body.appendChild(overlay);
  document.body.style.overflow = 'hidden';

  function close(cancelled) {
    document.body.removeChild(overlay);
    document.body.style.overflow = '';
    if (cancelled && typeof onCancel === 'function') onCancel();
  }

  overlay.querySelector('#_cfm_ok').addEventListener('click', function () {
    document.body.removeChild(overlay);
    document.body.style.overflow = '';
    onOk();
  });
  overlay.querySelector('#_cfm_cancel').addEventListener('click', function () { close(true); });
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) close(true);
  });
}

/* ── data-confirm-msg 属性を持つボタンに削除確認を自動登録 ── */
(function () {
  document.querySelectorAll('[data-confirm-msg]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var msg  = btn.dataset.confirmMsg;
      var form = document.getElementById(btn.dataset.form);
      if (!form) {
        console.error('showConfirm: form not found:', btn.dataset.form);
        return;
      }
      showConfirm(msg, function () { form.submit(); });
    });
  });
}());

// ── カスタムスクロールバー（Safari対応） ──
document.addEventListener('DOMContentLoaded', function () {
  const scroll = document.querySelector('.table-scroll');
  if (!scroll) return;

  // 横スクロールバー（テーブルの下）
  const hBar = document.createElement('div');
  const hThumb = document.createElement('div');
  hBar.style.cssText = `
    width: 100%;
    height: 8px;
    background: #ddd;
    border-radius: 4px;
    margin-top: 6px;
    position: relative;
    cursor: pointer;
  `;
  hThumb.style.cssText = `
    height: 100%;
    background: #888;
    border-radius: 4px;
    position: absolute;
    top: 0;
  `;
  hBar.appendChild(hThumb);
  scroll.parentNode.insertBefore(hBar, scroll.nextSibling);

  // 縦スクロールバー（テーブルの右）
  const vBar = document.createElement('div');
  const vThumb = document.createElement('div');
  vBar.style.cssText = `
    width: 8px;
    background: #ddd;
    border-radius: 4px;
    position: absolute;
    right: 0;
    top: 0;
    cursor: pointer;
  `;
  vThumb.style.cssText = `
    width: 100%;
    background: #888;
    border-radius: 4px;
    position: absolute;
    left: 0;
  `;
  vBar.appendChild(vThumb);
  scroll.style.position = 'relative';
  scroll.parentNode.style.position = 'relative';
  scroll.parentNode.appendChild(vBar);

  // 位置を更新する関数
  function update() {
    const hRatio = scroll.clientWidth / scroll.scrollWidth;
    hThumb.style.width = (hRatio * 100) + '%';
    hThumb.style.left = (scroll.scrollLeft / scroll.scrollWidth * 100) + '%';

    vBar.style.height = scroll.clientHeight + 'px';
    const vRatio = scroll.clientHeight / scroll.scrollHeight;
    vThumb.style.height = (vRatio * 100) + '%';
    vThumb.style.top = (scroll.scrollTop / scroll.scrollHeight * 100) + '%';
  }

  scroll.addEventListener('scroll', update);
  window.addEventListener('resize', update);
  update();
});
/* ===== カレンダー共通ユーティリティ（F-04 追加分） ===== */

// CSRF トークン取得
function getCsrfToken() {
  return document.cookie.split(';')
    .map(c => c.trim()).find(c => c.startsWith('csrftoken='))
    ?.split('=')[1] ?? '';
}

// 成功・エラートースト
function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'toast show';
  t.style.backgroundColor = type === 'error' ? '#dc3545' : '#2E75B6';
  t.textContent = msg;
  document.body.appendChild(t);
  // クリックでも閉じられるようにする
  t.addEventListener('click', () => { t.classList.add('hide'); setTimeout(() => t.remove(), 500); });
  setTimeout(() => { t.classList.add('hide'); setTimeout(() => t.remove(), 500); }, 3000);
}

// 「元に戻す」付きトースト（5秒）
function showUndoToast(msg, onUndo) {
  const t = document.createElement('div');
  t.className = 'toast show';
  t.style.backgroundColor = '#2E75B6';
  t.innerHTML = `${msg} <button style='margin-left:12px;background:none;border:1px solid #fff;
    color:#fff;cursor:pointer;border-radius:4px;padding:2px 8px;'>元に戻す</button>`;
  document.body.appendChild(t);
  const btn = t.querySelector('button');
  let done = false;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!done) { done = true; onUndo(); t.remove(); }
  });
  // トースト本体クリックで閉じる（ボタン以外の部分）
  t.addEventListener('click', () => { if (!done) { done = true; t.classList.add('hide'); setTimeout(() => t.remove(), 500); } });
  setTimeout(() => { if (!done) { done = true; t.classList.add('hide'); setTimeout(() => t.remove(), 500); } }, 5000);
}

// 日付フォーマット（例：5月14日(水) 10:00）
function formatDate(dt) {
  const days = ['日','月','火','水','木','金','土'];
  return `${dt.getMonth()+1}月${dt.getDate()}日(${days[dt.getDay()]})`;
}

// 時刻フォーマット（例：10:00）
function formatTime(dt) {
  if (!dt) return '';
  return dt.toTimeString().slice(0, 5);
}

/* ===== ナビメニュー（•••）開閉 — calendar・timeline 共通 ===== */
function toggleNavMenu(e) {
  e.stopPropagation();
  document.getElementById("navMenu")?.classList.toggle("open");
}

function toggleAdminSubmenu(e) {
  e.stopPropagation();
  document.getElementById("adminSubmenu")?.classList.toggle("open");
  document.getElementById("adminArrow")?.classList.toggle("expanded");
}

// メニュー外クリックで閉じる
document.addEventListener("click", function (e) {
  const navMenu = document.getElementById("navMenu");
  const dotsBtn = document.querySelector(".dots-btn");
  if (navMenu && navMenu.classList.contains("open")) {
    if (!navMenu.contains(e.target) && !dotsBtn?.contains(e.target)) {
      navMenu.classList.remove("open");
      document.getElementById("adminSubmenu")?.classList.remove("open");
      document.getElementById("adminArrow")?.classList.remove("open");
    }
  }
});