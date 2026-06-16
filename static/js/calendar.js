// ===== フィルターサイドバー 外クリックで閉じる（calendar 専用） =====
document.addEventListener("click", function (e) {
  const sidebar = document.getElementById('roomSidebar');
  const hamburger = document.querySelector('.hamburger-btn');
  if (sidebar && sidebar.classList.contains('open')) {
    if (!sidebar.contains(e.target) && !hamburger?.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  }
});


/* ===== フィルターセクション アコーディオン ===== */
function toggleFilterSection(headerEl) {
  const body  = headerEl.nextElementSibling;
  const arrow = headerEl.querySelector('.fsh-arrow');
  const willExpand = body.hidden;
  body.hidden = !willExpand;
  if (arrow) arrow.classList.toggle('expanded', willExpand);
}

/* ===== 予約詳細モーダル ===== */
function showReservationModal(el) {
  document.getElementById("modal-title").textContent = el.dataset.title;
  document.getElementById("modal-reserved-by").textContent =
    el.dataset.reservedBy;
  document.getElementById("modal-time").textContent =
    el.dataset.start + " 〜 " + el.dataset.end;
  document.getElementById("modal-detail-link").href =
    "/reservations/" + el.dataset.reservationId + "/";
  document.getElementById("reservationModal").classList.add("open");
}

function closeModal() {
  document.getElementById("reservationModal").classList.remove("open");
}

function closeModalOnOverlay(e) {
  if (e.target === document.getElementById("reservationModal")) closeModal();
}

document.addEventListener('DOMContentLoaded', function () {
  const el = document.getElementById('fullcalendar');
  const rooms = JSON.parse(el.dataset.rooms || '[]');
  //　↓コメントアウト。日次表示の設定を追加　20260605
  //const fcView = el.dataset.fcView || 'timeGridWeek';
  const fcView =window.innerWidth <= 768 ? 'timeGridDay' : (el.dataset.fcView || 'timeGridWeek');
  const _now = new Date();
  const initialDate = el.dataset.date ||
    `${_now.getFullYear()}-${String(_now.getMonth()+1).padStart(2,'0')}-${String(_now.getDate()).padStart(2,'0')}`;

  // 会議室フィルタ（localStorage から復元）
  const selectedIds = getSelectedRoomIds();

  const calendar = new FullCalendar.Calendar(el, {
    locale: 'ja',
    allDayText: '終日',
    initialView: fcView,
    initialDate: initialDate,
    firstDay: 1,  // 月曜始まり
    slotMinTime: '08:00:00',
    slotMaxTime: '22:00:00',
    slotDuration: '00:15:00',
    snapDuration: '00:15:00',
    scrollTime: '08:00:00',
    nowIndicator: true,
    dayMaxEvents: 2,
    allDaySlot: false,     // 終日行を非表示（終日予約はメイングリッドに 08:00〜22:00 で表示）
    editable: true,
    selectable: true,
    headerToolbar: false,  // カスタムツールバー使用
    // 時刻を常に HH:MM 形式で表示（日本語ロケールのデフォルト「10時」を上書き）
    eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
    // タイムライン左の時間ラベルを「8:00」形式に（ja ロケールのデフォルト「8時」を上書き）
    slotLabelFormat: { hour: 'numeric', minute: '2-digit', hour12: false },
    views: {
      dayGridMonth: { displayEventTime: true },
    },
    // 月ビュー：「● 終日/HH:MM 件名」形式で統一。週・日ビューはデフォルトと同等の HTML を返す
    eventContent: (arg) => {
      const ep    = arg.event.extendedProps;
      const title = arg.event.title.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const room  = (ep.room_name   || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const reserver = (ep.reserved_by || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const isRakumo      = !!ep.is_rakumo;
      const isAlldayDisp  = !!ep.display_as_allday;
      const rakumoBadge = '<span style="display:inline-block;background:#718096;color:#fff;font-size:13px;' +
        'font-weight:700;padding:2px 7px;border-radius:3px;margin-right:3px;' +
        'vertical-align:middle;line-height:1.4;">本社使用</span>';

      if (arg.view.type === 'dayGridMonth') {
        // 月ビュー：ドット + 時刻ラベル + (Rakumoならバッジのみ / 通常なら件名+予約者)
        const color = arg.event.backgroundColor || '#3182CE';
        // 終日表示イベントは時刻の代わりに「終日」ラベルを出す
        const label = isAlldayDisp ? '終日' : arg.timeText;
        if (isRakumo) {
          const roomSub = room ? '<span class="mev-sub">' + room + '</span>' : '';
          return {
            html: '<span class="mev-dot" style="background-color:' + color + '"></span>' +
                  '<span class="mev-time">' + label + '</span>' +
                  rakumoBadge + roomSub,
          };
        }
        const subParts = [room, reserver].filter(Boolean);
        const sub = subParts.length
          ? '<span class="mev-sub">' + subParts.join(' ／ ') + '</span>'
          : '';
        return {
          html: '<span class="mev-dot" style="background-color:' + color + '"></span>' +
                '<span class="mev-time">' + label + '</span>' +
                '<span class="mev-title">&nbsp;' + title + '</span>' +
                sub,
        };
      }

      // 週・日ビュー
      if (isRakumo) {
        // Rakumo：バッジ + 会議室名（件名・予約者非表示）
        const roomSubHtml = room ? '<div class="fc-event-sub">' + room + '</div>' : '';
        if (arg.timeText) {
          return {
            html: '<div class="fc-event-main-frame">' +
                  '<div class="fc-event-title-container">' +
                  '<div class="fc-event-title fc-sticky">' + rakumoBadge + '</div>' +
                  roomSubHtml +
                  '<div class="fc-event-time">' + arg.timeText + '</div>' +
                  '</div></div>',
          };
        }
        return {
          html: '<div class="fc-event-main-frame">' +
                '<div class="fc-event-title-container">' +
                '<div class="fc-event-title fc-sticky">' + rakumoBadge + '</div>' +
                roomSubHtml +
                '</div></div>',
        };
      }

      // 週・日ビュー（通常予約）：件名の下に「会議室 ／ 予約者」を小さく表示
      const subParts = [room, reserver].filter(Boolean);
      const subHtml = subParts.length
        ? '<div class="fc-event-sub">' + subParts.join(' ／ ') + '</div>'
        : '';

      if (arg.timeText) {
        return {
          html: '<div class="fc-event-main-frame">' +
                '<div class="fc-event-title-container">' +
                '<div class="fc-event-title fc-sticky">' + title + '</div>' +
                subHtml +
                '<div class="fc-event-time">' + arg.timeText + '</div>' +
                '</div></div>',
        };
      }
      return {
        html: '<div class="fc-event-main-frame">' +
              '<div class="fc-event-title-container">' +
              '<div class="fc-event-title fc-sticky">' + title + '</div>' +
              subHtml +
              '</div></div>',
      };
    },
    eventSources: [{ url: '/reservations/events/',
      extraParams: () => {
        const params = { room_ids: getSelectedRoomIds().join(',') };
        // 各フィルターが「全選択」でない場合のみパラメータを追加する
        // 全選択時はパラメータ自体を送らない（バックエンドでフィルターなし扱い）
        const addFilter = (paramName, cls) => {
          const v = getFilterParam(cls);
          if (v !== 'all') params[paramName] = v;
        };
        addFilter('building_ids',   'building-checkbox');
        addFilter('facility_ids',   'facility-checkbox');
        addFilter('department_ids', 'department-checkbox');
        addFilter('user_ids',       'user-checkbox');
        return params;
      },
    }],
    eventClick: handleEventClick,
    eventDrop: handleEventDrop,
    eventResize: handleEventResize,
    dateClick: handleDateClick,
    select: handleSelect,
    datesSet: handleDatesSet,
    eventDidMount: (info) => {
      if (info.view.type === 'dayGridMonth') {
        // 月ビュー：背景色を除去して文字色を黒に固定
        info.el.style.backgroundColor = 'transparent';
        info.el.style.borderColor     = 'transparent';
        info.el.style.boxShadow       = 'none';
        info.el.style.color           = '#1A1A2E';
      } else {
        // 週・日ビュー：背景色に応じて白 or 黒を選択
        info.el.style.color = getTextColor(info.event.backgroundColor || '#3182CE');
      }
      // can_edit が false の場合のみ DnD を無効化（display_as_allday は can_edit で制御）
      if (!info.event.extendedProps.can_edit) {
        info.el.setAttribute('draggable', 'false');
        info.el.style.cursor = 'default';
      }
    },
  });
  window.calendar = calendar;
  calendar.render();
});

// DnD コールバック（eventDrop / eventResize 共通）
function handleEventDrop(info) {
  const res          = info.event;
  const isAllDay     = res.allDay;
  const isAlldayDisp = !!res.extendedProps.display_as_allday;

  // display_as_allday な終日予約はドロップ先の「日付」だけ使い、終日予約として保存する
  const treatAsAllday = isAllDay || isAlldayDisp;

  // 確認メッセージ
  const msg = treatAsAllday
    ? `${formatDate(res.start)} 終日\nに変更しますか？`
    : `${formatDate(res.start)} ${formatTime(res.start)}〜${formatTime(res.end)}\nに変更しますか？`;

  // API へ送るペイロード
  const payload = {
    room_id:    res.extendedProps.room_id,
    is_all_day: treatAsAllday,
  };
  if (treatAsAllday) {
    // 終日の場合は日付文字列だけ送る（toISOString() はタイムゾーンで日付がずれる場合があるため）
    if (isAlldayDisp) {
      // display_as_allday イベントは 08:00 起点のためローカル日付で抽出する
      const d = res.start;
      payload.date = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    } else {
      payload.date = res.startStr.slice(0, 10);  // 'YYYY-MM-DD'
    }
  } else {
    payload.start_at = res.start.toISOString();
    // 終日→通常への切り替え時に res.end が null になる場合があるため、
    // その場合は開始時刻の30分後をデフォルトとする
    const endDate = res.end || new Date(res.start.getTime() + 30 * 60 * 1000);
    payload.end_at = endDate.toISOString();
  }

  showConfirm(
    msg,
    () => {  // OK：API 呼び出し
      fetch(`/reservations/${res.id}/move/`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json',
                  'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify(payload)
      })
      .then(r => {
        if (!r.ok) {
          // レスポンスが JSON でない場合（Django エラーページ等の HTML）でも
          // 安全にエラーメッセージを取り出す
          return r.text().then(text => {
            let msg = '変更に失敗しました';
            try {
              const d = JSON.parse(text);
              if (d.error) msg = d.error;
            } catch (_) { /* HTML レスポンスは無視して汎用メッセージを使う */ }
            throw new Error(msg);
          });
        }
        // 終日→通常への切り替え時に res.end が null の場合、
        // FullCalendar のイベントオブジェクトを更新してブロックを正しく描画する
        if (!isAllDay && !res.end) {
          const fixedEnd = new Date(res.start.getTime() + 30 * 60 * 1000);
          info.event.setEnd(fixedEnd);
        }
        showUndoToast('予約を変更しました', () => { info.revert(); });
      })
      .catch(err => {
        showToast(err.message || '変更に失敗しました', 'error');
        info.revert();
      });
    },
    () => { info.revert(); },  // キャンセル：元の位置に戻す
    '変更する',                // OK ボタンのラベル
    'btn-primary',             // OK ボタンの色（青）
    '戻る'                     // 戻るボタンのラベル
  );
}

// eventResize コールバック — 同一日内のリサイズのみ許可
function handleEventResize(info) {
  const res = info.event;

  if (res.start && res.end) {
    // 開始日を日単位に正規化
    const startDay = new Date(res.start);
    startDay.setHours(0, 0, 0, 0);

    // 終了が翌日 00:00:00（= 当日の末端）の場合は同日扱い
    const endDay = new Date(res.end);
    if (endDay.getHours() === 0 && endDay.getMinutes() === 0 && endDay.getSeconds() === 0) {
      endDay.setDate(endDay.getDate() - 1);
    }
    endDay.setHours(0, 0, 0, 0);

    if (startDay.getTime() !== endDay.getTime()) {
      info.revert();
      showToast('予約の時間変更は同じ日の範囲内のみ可能です', 'error');
      return;
    }
  }

  // 同一日内 → 通常の移動・更新ロジックへ
  handleEventDrop(info);
}

// 月ビューでは eventClick と dateClick が同時発火するため、
// eventClick が先に走ったことをフラグで記録して dateClick 側でガードする
let _eventJustClicked = false;

// eventClick コールバック — ポップオーバー表示
function handleEventClick(info) {
  _eventJustClicked = true;
  setTimeout(() => { _eventJustClicked = false; }, 0);
  const ev = info.event;
  const ep = ev.extendedProps;
  const po = document.querySelector('.reservation-popover');

  // 内容を更新
  const isRakumoEv = !!ep.is_rakumo;
  po.querySelector('.popover-title').textContent = isRakumoEv ? '本社使用' : ev.title;
  po.querySelector('.popover-title').style.backgroundColor = ev.backgroundColor;
  po.querySelector('[data-field="datetime"]').textContent = ep.display_as_allday
    ? `${formatDate(ev.start)} 終日`
    : `${formatDate(ev.start)} ${formatTime(ev.start)}〜${formatTime(ev.end)}`;
  po.querySelector('[data-field="room"]').textContent = ep.room_name;
  // Rakumo予約は予約者を非表示
  const reserverRow = po.querySelector('[data-field="reserver"]')?.closest('p');
  if (reserverRow) reserverRow.style.display = isRakumoEv ? 'none' : '';
  po.querySelector('[data-field="reserver"]').textContent = isRakumoEv ? '' : ep.reserved_by;

  // 権限に応じてボタン表示
  const editBtn    = po.querySelector('.btn-edit');
  const cancelForm = po.querySelector('#popover-cancel-form');
  const cancelBtn  = po.querySelector('.btn-cancel');
  const detailBtn  = po.querySelector('.btn-detail');

  editBtn.style.display    = ep.can_edit ? '' : 'none';  // 編集：自分の予約 or 管理者
  cancelForm.style.display = ep.can_edit ? '' : 'none';  // キャンセル：自分の予約 or 管理者
  // Rakumo予約は詳細ページなし
  detailBtn.style.display  = isRakumoEv ? 'none' : '';
  editBtn.href     = `/reservations/${ev.id}/edit/`;
  detailBtn.href   = `/reservations/${ev.id}/`;

  // キャンセルフォーム：action をセットして onsubmit で確認ダイアログ
  cancelForm.action   = `/reservations/${ev.id}/cancel/`;
  cancelForm.onsubmit = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const datetime = `${formatDate(ev.start)} ${formatTime(ev.start)}〜${formatTime(ev.end)}`;
    showConfirm(
      `「${ev.title}（${datetime}）」をキャンセルしますか？\nこの操作は取り消せません。`,
      () => { cancelForm.submit(); },
      null,
      'キャンセルする',
      'btn-danger',
      '戻る',
      '予約のキャンセル確認'
    );
  };

  // 位置を調整して表示（画面端からはみ出ないよう補正）
  po.hidden = false;
  const margin = 10;
  const poW = po.offsetWidth  || 280;
  const poH = po.offsetHeight || 200;
  const vw  = window.innerWidth;
  const vh  = window.innerHeight;
  const cx  = info.jsEvent.clientX;
  const cy  = info.jsEvent.clientY;

  // 左右：右に出しきれない場合は左側に表示
  let left = cx + margin;
  if (left + poW > vw - margin) left = cx - poW - margin;
  if (left < margin) left = margin;

  // 上下：下に出しきれない場合は上側に表示
  let top = cy + margin;
  if (top + poH > vh - margin) top = cy - poH - margin;
  if (top < margin) top = margin;

  po.style.left = `${left}px`;
  po.style.top  = `${top}px`;

  info.jsEvent.stopPropagation();
}

// 外クリックで閉じる
document.addEventListener('click', () => {
  document.querySelector('.reservation-popover').hidden = true;
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape')
    document.querySelector('.reservation-popover').hidden = true;
});

// 会議室選択状態の localStorage 連携
const STORAGE_KEY = 'calendar_room_selection';

function getSelectedRoomIds() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : getRoomIds(); // 未保存は全室
  } catch { return getRoomIds(); }
}

function saveSelectedRoomIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

// ページロード時：localStorage の選択状態をチェックボックス UI に反映
(function restoreCheckboxState() {
  const saved  = localStorage.getItem(STORAGE_KEY);
  const allIds = getRoomIds();

  let savedIds;
  if (saved === null) {
    // 未保存：全室選択
    savedIds = allIds.slice();
  } else {
    savedIds = JSON.parse(saved);
    // 新規登録された会議室（localStorage に存在しないもの）は自動でチェック追加
    const newIds = allIds.filter(id => !savedIds.includes(id));
    if (newIds.length > 0) {
      savedIds = savedIds.concat(newIds);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(savedIds));
    }
  }

  const isAll = savedIds.length === allIds.length;
  document.querySelectorAll('.room-checkbox').forEach(cb => {
    cb.checked = savedIds.includes(parseInt(cb.value));
  });
  const selectAllCb = document.getElementById('selectAllRooms');
  if (selectAllCb) selectAllCb.checked = isAll;
}());

// 個別会議室チェックボックス変更時
document.querySelectorAll('.room-checkbox').forEach(cb => {
  cb.addEventListener('change', () => {
    const ids = Array.from(
      document.querySelectorAll('.room-checkbox:checked'),
      el => parseInt(el.value)
    );
    saveSelectedRoomIds(ids);

    // 「全会議室」チェックボックスの状態を同期
    const selectAllCb = document.getElementById('selectAllRooms');
    if (selectAllCb) selectAllCb.checked = ids.length === getRoomIds().length;

    window.calendar?.refetchEvents();  // window.calendar を参照（DOMContentLoaded 外のため）
  });
});

// 「全会議室」チェックボックス変更時
document.getElementById('selectAllRooms')?.addEventListener('change', function () {
  const checked = this.checked;
  document.querySelectorAll('.room-checkbox').forEach(cb => { cb.checked = checked; });
  const ids = checked ? getRoomIds() : [];
  saveSelectedRoomIds(ids);
  window.calendar?.refetchEvents();
});

// ======== 追加フィルター（建物・設備・所属・予約者）========

const EXTRA_FILTER_GROUPS = [
  { checkboxClass: 'building-checkbox',   group: 'building',   storageKey: 'calendar_filter_building'   },
  { checkboxClass: 'facility-checkbox',   group: 'facility',   storageKey: 'calendar_filter_facility'   },
  { checkboxClass: 'department-checkbox', group: 'department', storageKey: 'calendar_filter_department' },
  { checkboxClass: 'user-checkbox',       group: 'user',       storageKey: 'calendar_filter_user'       },
];

EXTRA_FILTER_GROUPS.forEach(({ checkboxClass, group, storageKey }) => {
  const allCbs     = document.querySelectorAll(`.${checkboxClass}`);
  if (!allCbs.length) return;
  const selectAllCb = document.querySelector(`.filter-all-cb[data-group="${group}"]`);

  // ── localStorage から選択状態を復元 ──────────────────────
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved !== null) {
      let savedIds = JSON.parse(saved).map(String);
      const allIds = Array.from(allCbs, cb => cb.value);
      // 新規登録された項目（localStorage に存在しないもの）は自動でチェック追加
      const newIds = allIds.filter(id => !savedIds.includes(id));
      if (newIds.length > 0) {
        savedIds = savedIds.concat(newIds);
        localStorage.setItem(storageKey, JSON.stringify(savedIds.map(Number)));
      }
      allCbs.forEach(cb => { cb.checked = savedIds.includes(cb.value); });
      if (selectAllCb) selectAllCb.checked = savedIds.length === allCbs.length;
    }
  } catch { /* 復元失敗時はデフォルト（全選択）のまま */ }

  // ── 個別チェックボックス変更時 ────────────────────────────
  allCbs.forEach(cb => {
    cb.addEventListener('change', () => {
      const checkedIds = Array.from(allCbs).filter(c => c.checked).map(c => parseInt(c.value));
      localStorage.setItem(storageKey, JSON.stringify(checkedIds));
      if (selectAllCb) selectAllCb.checked = checkedIds.length === allCbs.length;
      window.calendar?.refetchEvents();
    });
  });

  // ── 「すべて」チェックボックス変更時 ─────────────────────
  selectAllCb?.addEventListener('change', function () {
    allCbs.forEach(cb => { cb.checked = this.checked; });
    const ids = this.checked ? Array.from(allCbs, cb => parseInt(cb.value)) : [];
    localStorage.setItem(storageKey, JSON.stringify(ids));
    window.calendar?.refetchEvents();
  });
});

// RRULE 生成ユーティリティ
function buildRRule(pattern, days, endType, endValue) {
  const DAY_MAP = {mon:'MO',tue:'TU',wed:'WE',thu:'TH',fri:'FR',sat:'SA',sun:'SU'};
  let rule = '';
  if      (pattern === 'daily')   rule = 'FREQ=DAILY';
  else if (pattern === 'weekly') {
    const byDay = days.map(d => DAY_MAP[d]).join(',');
    rule = `FREQ=WEEKLY;BYDAY=${byDay}`;
  }
  else if (pattern === 'monthly') rule = 'FREQ=MONTHLY';
  if (endType === 'count') rule += `;COUNT=${endValue}`;
  if (endType === 'until') {
    const dt = endValue.replace(/-/g,'') + 'T000000Z';
    rule += `;UNTIL=${dt}`;
  }
  return rule;  // 例: FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10
}

// 輝度計算ユーティリティ（F-04-R04）
// 参考: WCAG 2.1 相対輝度 https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
function getTextColor(hexColor) {
  // HEX → RGB（0〜255）
  const r = parseInt(hexColor.slice(1, 3), 16);
  const g = parseInt(hexColor.slice(3, 5), 16);
  const b = parseInt(hexColor.slice(5, 7), 16);

  // 線形化（ガンマ補正を除去）
  const toLinear = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };

  // 相対輝度 L = 0.2126R + 0.7152G + 0.0722B
  const L = 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);

  // 閾値 0.179 を境に白 or 黒を返す
  return L > 0.179 ? '#1A1A2E' : '#FFFFFF';
}

// 同期 ON/OFF トグル
document.getElementById('google-sync-toggle')?.addEventListener('change', function () {
  fetch('/auth/google/sync-toggle/', {
    method: 'PATCH',
    headers: {'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json'},
    body: JSON.stringify({})
  })
  .then(r => r.json())
  .then(data => {
    const label = document.getElementById('sync-status-label');
    if (label) label.textContent = data.sync_enabled ? '同期中' : '一時停止中';
    showToast(data.sync_enabled ? 'Google 同期を有効にしました' : 'Google 同期を一時停止しました');
  })
  .catch(() => showToast('エラーが発生しました', 'error'));
});

// 連携解除
document.getElementById('google-disconnect-btn')?.addEventListener('click', function () {
  showConfirm('Google カレンダーとの連携を解除しますか？\n解除後は新規予約の同期が停止されます。', () => {
    fetch('/auth/google/disconnect/', {
      method: 'POST',
      headers: {'X-CSRFToken': getCsrfToken()}
    })
    .then(r => { if (r.ok) location.reload(); })
    .catch(() => showToast('連携解除に失敗しました', 'error'));
  });
});

/* ===== F-04 追加ユーティリティ ===== */

// FullCalendar の現在日付をローカルタイムゾーンで 'YYYY-MM-DD' 形式で返す
// （toISOString() は UTC 変換のため日本時間では日付がずれる場合がある）
function getCalDateStr() {
  const d    = window.calendar.getDate();
  const yyyy = d.getFullYear();
  const mm   = String(d.getMonth() + 1).padStart(2, '0');
  const dd   = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * 指定クラスのチェックボックス群からフィルターパラメータ値を生成する
 * - 全選択（または0件）: 'all'  → パラメータ自体を送らない
 * - 一部選択: '1,2,3'
 * - 全未選択: ''  → バックエンドで0件を返す
 */
function getFilterParam(checkboxClass) {
  const allCbs     = document.querySelectorAll(`.${checkboxClass}`);
  if (!allCbs.length) return 'all';
  const checkedVals = Array.from(allCbs).filter(cb => cb.checked).map(cb => cb.value);
  if (checkedVals.length === allCbs.length) return 'all';
  return checkedVals.join(',');
}

// 全会議室 ID 一覧（data-rooms から取得）
function getRoomIds() {
  const el = document.getElementById('fullcalendar');
  if (!el) return [];
  const rooms = JSON.parse(el.dataset.rooms || '[]');
  return rooms.map(r => r.id);
}

// ツールバータイトル更新（ビュー変更・日付移動のたびに呼ばれる）
function handleDatesSet(info) {
  const view  = info.view.type;
  const start = info.start;                        // 表示開始日（グリッド上の最初のセル）
  const end   = new Date(info.end.getTime() - 1); // 表示終了日（exclusive を inclusive に）

  // 月表示では currentStart を使う。
  // info.start はグリッド先頭（前月末の日付になる場合がある）のため、
  // currentStart（当月1日）を使うことで正しい年月を取得できる。
  const cur = info.view.currentStart;

  // M月D日 形式
  const fmt = (dt) => `${dt.getMonth() + 1}月${dt.getDate()}日`;

  let title = '';
  if (view === 'timeGridDay') {
    // 日表示：「2026年5月18日」
    title = `${start.getFullYear()}年${start.getMonth() + 1}月${start.getDate()}日`;
  } else if (view === 'timeGridWeek') {
    // 週表示：「2026年 5月18日 - 5月24日」
    title = `${start.getFullYear()}年 ${fmt(start)} - ${fmt(end)}`;
  } else if (view === 'dayGridMonth') {
    // 月表示：「2026年5月」（currentStart で当月を正確に取得）
    title = `${cur.getFullYear()}年${cur.getMonth() + 1}月`;
  } else {
    title = info.view.title;
  }

  const calTitle = document.getElementById('calTitle');
  if (calTitle) calTitle.textContent = title;
}

// 月次ビューで日付クリック → 日次ビューへ遷移
// ※ イベントブロッククリック時は _eventJustClicked フラグでスキップ
function handleDateClick(info) {
  if (_eventJustClicked) return;

  if (info.view.type === 'dayGridMonth') {
    // 月ビュー → その日の日ビューへ
    location.href = `?view=day&date=${info.dateStr}`;
    return;
  }

  // 日・週ビュー → 予約作成画面へ
  const dateStr = info.dateStr.slice(0, 10);
  let url;

  if (info.allDay) {
    // 終日行クリック → all_day=1 を渡す
    url = `/reservations/create/?date=${dateStr}&all_day=1`;
  } else {
    const timeStr = info.dateStr.slice(11, 16);
    url = `/reservations/create/?date=${dateStr}&time=${timeStr}`;
  }

  const selectedIds = getSelectedRoomIds();
  if (selectedIds.length === 1) {
    url += `&room=${selectedIds[0]}`;
  }
  location.href = url;
}

// 空きスロット選択 → 予約作成画面へ遷移（F-09 カレンダー連携）
function handleSelect(info) {
  const startDateStr = info.startStr.slice(0, 10);  // 'YYYY-MM-DD'

  // ── 日をまたぐ選択を禁止 ──────────────────────────────────────
  if (info.allDay) {
    // 終日選択：end は exclusive のため「開始日の翌日 = 単一日」
    const startTs = new Date(startDateStr).getTime();
    const endTs   = new Date(info.endStr.slice(0, 10)).getTime();
    const diffDays = (endTs - startTs) / (1000 * 60 * 60 * 24);
    if (diffDays > 1) {
      window.calendar?.unselect();
      showToast('予約登録は同じ日の範囲内のみ可能です', 'error');
      return;
    }
  } else {
    // 時間選択：終了が 00:00:00 の場合は前日の末端として扱う
    const endDt = info.end;  // Date オブジェクト
    let effectiveEndDateStr;
    if (endDt && endDt.getHours() === 0 && endDt.getMinutes() === 0 && endDt.getSeconds() === 0) {
      const prev = new Date(endDt.getTime() - 60000);  // 1分前 = 23:59
      effectiveEndDateStr =
        `${prev.getFullYear()}-` +
        `${String(prev.getMonth() + 1).padStart(2, '0')}-` +
        `${String(prev.getDate()).padStart(2, '0')}`;
    } else {
      effectiveEndDateStr = info.endStr.slice(0, 10);
    }
    if (startDateStr !== effectiveEndDateStr) {
      window.calendar?.unselect();
      showToast('予約登録は同じ日の範囲内のみ可能です', 'error');
      return;
    }
  }
  // ─────────────────────────────────────────────────────────────

  let url;
  if (info.allDay) {
    // 終日スロット選択：all_day=1 を渡してフォームを終日モードで開く
    url = `/reservations/create/?date=${startDateStr}&all_day=1`;
  } else {
    const timeStr    = info.startStr.slice(11, 16);  // 'HH:MM'（開始時刻）
    const endTimeStr = info.endStr.slice(11, 16);    // 'HH:MM'（終了時刻：ドラッグ終端）
    url = `/reservations/create/?date=${startDateStr}&time=${timeStr}&end_time=${endTimeStr}`;
  }

  // サイドバーで1室のみ選択中なら room を自動補完
  const selectedIds = getSelectedRoomIds();
  if (selectedIds.length === 1) {
    url += `&room=${selectedIds[0]}`;
  }
  location.href = url;
}