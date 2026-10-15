#include <pebble.h>
#include <stdio.h>
#include <string.h>

#define ROWS 6
#define CACHE_KEY 100
#define CACHE_VERSION 2
#define INBOX 1024

typedef struct {
  char ticker[24], value[24], daily[32], detail[701];
} Holding;
typedef struct {
  uint32_t version, updated;
  char account[32], value[24], change[24], percent[20];
  bool demo, hide, valid;
} Summary;
typedef struct {
  Summary summary;
  Holding holdings[ROWS];
  uint8_t count, page, pages, received;
  uint16_t total_count;
  uint32_t generation;
  uint8_t chart[24], chart_count;
  char chart_label[32], note[128], error[32];
} Snapshot;

static Window *s_main, *s_list, *s_detail, *s_info;
static Layer *s_canvas;
static StatusBarLayer *s_bar;
static MenuLayer *s_menu;
static ScrollLayer *s_detail_scroll, *s_info_scroll;
static TextLayer *s_detail_text, *s_info_text, *s_list_status;
static char s_list_status_buffer[96];
static void age_text(char *out, size_t size);
static bool stale(void);
static void update_detail(void);
static Snapshot s_data, s_pending;
static char s_state[32], s_info_buffer[800], s_detail_buffer[850];
static bool s_loading, s_receiving, s_cached_only, s_local_hide;
static bool hidden(void) { return s_local_hide || s_data.summary.hide; }
static uint8_t s_card;
static int s_selected = -1;
static AppTimer *s_timeout, *s_launch_timer;
static ActionMenuLevel *s_actions;
static ActionMenu *s_action_menu;

static void redraw(void) {
  if (s_detail && window_stack_contains_window(s_detail))
    update_detail();
  if (s_canvas)
    layer_mark_dirty(s_canvas);
  if (s_menu)
    menu_layer_reload_data(s_menu);
  if (s_list_status) {
    char age[40];
    age_text(age, sizeof(age));
    snprintf(s_list_status_buffer, sizeof(s_list_status_buffer),
             "%sHoldings %d/%d\n%s%s", s_data.summary.demo ? "DEMO " : "",
             s_data.page + 1, s_data.pages, stale() ? "STALE | " : "", age);
    text_layer_set_text(s_list_status, s_list_status_buffer);
  }
}
static void set_state(const char *state) {
  snprintf(s_state, sizeof(s_state), "%s", state);
  redraw();
}
static const char *state_label(void) {
  if (!strcmp(s_state, "SETUP"))
    return "Set up on phone";
  if (!strcmp(s_state, "AUTH_REQUIRED") || !strcmp(s_state, "AUTH_EXPIRED"))
    return "Reconnect account";
  if (!strcmp(s_state, "PHONE_OFFLINE"))
    return "Phone disconnected";
  if (!strcmp(s_state, "NO_INTERNET"))
    return "No internet";
  if (!strcmp(s_state, "SCHEMA_UNVERIFIED"))
    return "Live setup pending";
  if (!strcmp(s_state, "RATE_LIMITED"))
    return "Please wait";
  if (!strcmp(s_state, "STALE"))
    return "Stale data";
  if (!strcmp(s_state, "DEMO_SETTINGS"))
    return "Demo build";
  if (!strcmp(s_state, "EMPTY_ACCOUNTS"))
    return "No accounts";
  if (!strcmp(s_state, "CONFIG_INVALID"))
    return "Settings not saved";
  return "Provider unavailable";
}
static bool stale(void) {
  time_t now = time(NULL);
  return s_data.summary.valid &&
         (s_state[0] || now < (time_t)s_data.summary.updated ||
          now - s_data.summary.updated > 300);
}
static void age_text(char *out, size_t size) {
  long age = (long)time(NULL) - (long)s_data.summary.updated;
  if (age < 0)
    snprintf(out, size, "Clock mismatch");
  else if (age < 60)
    snprintf(out, size, "Updated just now");
  else if (age < 3600)
    snprintf(out, size, "Updated %ldm ago", age / 60);
  else if (age < 86400)
    snprintf(out, size, "Updated %ldh ago", age / 3600);
  else
    snprintf(out, size, "Updated %ldd ago", age / 86400);
}
static void update_detail(void) {
  if (s_selected < 0 || s_selected >= s_data.count || !s_detail_text)
    return;
  char age[40];
  age_text(age, sizeof(age));
  snprintf(s_detail_buffer, sizeof(s_detail_buffer), "%s%s\n%s\n%s",
           s_data.summary.demo ? "DEMO | " : "", stale() ? "STALE" : age,
           stale() ? age : "USD",
           hidden() ? "Balances hidden. Turn off hide mode to view details."
                    : s_data.holdings[s_selected].detail);
  text_layer_set_text(s_detail_text, s_detail_buffer);
  GSize size = text_layer_get_content_size(s_detail_text);
  scroll_layer_set_content_size(s_detail_scroll, GSize(size.w, size.h + 14));
}
static void short_age(char *out, size_t size) {
  long age = (long)time(NULL) - (long)s_data.summary.updated;
  if (age < 0)
    snprintf(out, size, "Clock?");
  else if (age < 60)
    snprintf(out, size, "now");
  else if (age < 3600)
    snprintf(out, size, "%ldm old", age / 60);
  else if (age < 86400)
    snprintf(out, size, "%ldh old", age / 3600);
  else
    snprintf(out, size, "%ldd old", age / 86400);
}
static void draw_text(GContext *ctx, const char *text, const char *font,
                      GRect rect, GTextAlignment alignment) {
  graphics_draw_text(ctx, text, fonts_get_system_font(font), rect,
                     GTextOverflowModeTrailingEllipsis, alignment, NULL);
}
static void canvas_update(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  int w = b.size.w, h = b.size.h;
  graphics_context_set_fill_color(ctx, GColorWhite);
  graphics_fill_rect(ctx, b, 0, GCornerNone);
  graphics_context_set_text_color(ctx, GColorBlack);
  if (!s_data.summary.valid) {
    draw_text(ctx, "PEBBLE HOOD", FONT_KEY_GOTHIC_24_BOLD,
              GRect(8, 4, w - 16, 32), GTextAlignmentLeft);
    draw_text(ctx, s_loading ? "Connecting..." : state_label(),
              FONT_KEY_GOTHIC_24_BOLD, GRect(8, 36, w - 16, 52),
              GTextAlignmentLeft);
    const char *hint = "Open settings in the Pebble phone app.";
    if (!strcmp(s_state, "PHONE_OFFLINE"))
      hint = "Connect your watch to the Pebble phone app.";
    if (!strcmp(s_state, "SCHEMA_UNVERIFIED"))
      hint = "Verify Robinhood fields. Demo is available in settings.";
    draw_text(ctx, hint, FONT_KEY_GOTHIC_18, GRect(8, 88, w - 16, h - 108),
              GTextAlignmentLeft);
    draw_text(ctx, "Select: options", FONT_KEY_GOTHIC_14,
              GRect(8, h - 20, w - 16, 20), GTextAlignmentLeft);
    return;
  }
  if (s_card) {
    draw_text(ctx, s_state[0] ? state_label() : "Data status",
              FONT_KEY_GOTHIC_24_BOLD, GRect(8, 0, w - 16, 55),
              GTextAlignmentLeft);
    char age[40];
    age_text(age, sizeof(age));
    draw_text(ctx, age, FONT_KEY_GOTHIC_18_BOLD, GRect(8, 56, w - 16, 24),
              GTextAlignmentLeft);
    draw_text(ctx,
              hidden()         ? "Balances hidden"
              : s_data.note[0] ? s_data.note
                               : "Saved overview. Refresh for holdings.",
              FONT_KEY_GOTHIC_18, GRect(8, 83, w - 16, h - 104),
              GTextAlignmentLeft);
    draw_text(ctx, "Select: options", FONT_KEY_GOTHIC_14,
              GRect(8, h - 20, w - 16, 20), GTextAlignmentLeft);
    return;
  }
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, GRect(0, 0, w, 25), 0, GCornerNone);
  graphics_context_set_text_color(ctx, GColorWhite);
  draw_text(ctx, s_data.summary.account, FONT_KEY_GOTHIC_18_BOLD,
            GRect(6, 0, w - 14, 25), GTextAlignmentLeft);
  graphics_context_set_text_color(ctx, GColorBlack);
  const char *font = strlen(s_data.summary.value) > 11
                         ? FONT_KEY_GOTHIC_24_BOLD
                         : FONT_KEY_GOTHIC_28_BOLD;
  draw_text(ctx, hidden() ? "Hidden" : s_data.summary.value, font,
            GRect(7, 29, w - 14, 38), GTextAlignmentLeft);
  char line[48];
  snprintf(line, sizeof(line), "Today %s",
           hidden() ? "Hidden" : s_data.summary.change);
#ifdef PBL_COLOR
  if (s_data.summary.change[0] == '+')
    graphics_context_set_text_color(ctx, GColorDarkGreen);
  else if (s_data.summary.change[0] == '-')
    graphics_context_set_text_color(ctx, GColorDarkCandyAppleRed);
#endif
  draw_text(ctx, line, FONT_KEY_GOTHIC_18_BOLD, GRect(7, 67, w - 14, 24),
            GTextAlignmentLeft);
  draw_text(ctx, hidden() ? "" : s_data.summary.percent,
            FONT_KEY_GOTHIC_18_BOLD, GRect(7, 88, w - 14, 24),
            GTextAlignmentLeft);
  graphics_context_set_text_color(ctx, GColorBlack);
  int chart_top = 117, chart_bottom = h - 38;
  if (h < 180) {
    chart_top = 112;
    chart_bottom = h - 24;
  }
  if (s_data.chart_count > 1 && !hidden() && chart_bottom > chart_top) {
    graphics_context_set_stroke_color(ctx, GColorBlack);
    for (int i = 1; i < s_data.chart_count; i++) {
      int x1 = 8 + (w - 22) * (i - 1) / (s_data.chart_count - 1),
          x2 = 8 + (w - 22) * i / (s_data.chart_count - 1);
      int y1 = chart_bottom -
               (chart_bottom - chart_top) * s_data.chart[i - 1] / 100,
          y2 =
              chart_bottom - (chart_bottom - chart_top) * s_data.chart[i] / 100;
      graphics_draw_line(ctx, GPoint(x1, y1), GPoint(x2, y2));
    }
  } else if (h > 180)
    draw_text(ctx, hidden() ? "Balances hidden" : "History unavailable",
              FONT_KEY_GOTHIC_18, GRect(7, 123, w - 14, 44),
              GTextAlignmentLeft);
  if (h > 180)
    draw_text(ctx, s_data.chart_label, FONT_KEY_GOTHIC_14,
              GRect(7, h - 37, w - 14, 18), GTextAlignmentLeft);
  char age[40], footer[60];
  age_text(age, sizeof(age));
  if (s_loading)
    snprintf(footer, sizeof(footer), "Refreshing...");
  else if (s_state[0]) {
    char compact_age[20];
    short_age(compact_age, sizeof(compact_age));
    const char *label = state_label();
    if (!strcmp(s_state, "PHONE_OFFLINE"))
      label = "Phone offline";
    else if (!strcmp(s_state, "PROVIDER_FAILURE"))
      label = "Provider error";
    snprintf(footer, sizeof(footer), "%s | %s", label, compact_age);
  } else if (stale())
    snprintf(footer, sizeof(footer), "STALE - %s", age);
  else if (!s_data.summary.demo && s_data.chart_count > 1) {
    char compact_age[20];
    short_age(compact_age, sizeof(compact_age));
    snprintf(footer, sizeof(footer), "Balances | %s", compact_age);
  } else
    snprintf(footer, sizeof(footer), "%s%s",
             s_data.summary.demo ? "DEMO | " : "", age);
  draw_text(ctx, footer, FONT_KEY_GOTHIC_14, GRect(7, h - 19, w - 12, 19),
            GTextAlignmentLeft);
  // Pebble's familiar Select affordance. Up/Down changes the two overview
  // cards.
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, GRect(w - 4, h / 2 - 8, 4, 16), 0, GCornerNone);
}

static void timeout(void *context) {
  s_timeout = NULL;
  s_loading = false;
  s_receiving = false;
  set_state("PHONE_OFFLINE");
}
static void stop_loading(void) {
  s_loading = false;
  if (s_timeout) {
    app_timer_cancel(s_timeout);
    s_timeout = NULL;
  }
}
static void request(uint8_t cmd, uint8_t page) {
  if (s_loading)
    return;
  if (!connection_service_peek_pebble_app_connection()) {
    set_state("PHONE_OFFLINE");
    return;
  }
  DictionaryIterator *out;
  if (app_message_outbox_begin(&out) != APP_MSG_OK) {
    set_state("PHONE_OFFLINE");
    return;
  }
  dict_write_uint8(out, MESSAGE_KEY_TYPE, 10);
  dict_write_uint8(out, MESSAGE_KEY_CMD, cmd);
  dict_write_uint8(out, MESSAGE_KEY_PAGE, page);
  if (app_message_outbox_send() != APP_MSG_OK) {
    set_state("PHONE_OFFLINE");
    return;
  }
  s_loading = true;
  redraw();
  s_timeout = app_timer_register(22000, timeout, NULL);
}
static void launch_refresh(void *context) {
  s_launch_timer = NULL;
  if (s_receiving || (s_data.summary.valid && !s_cached_only))
    return;
  stop_loading();
  request(0, 0);
}
static void show_info(ActionMenu *menu);
static void show_actions(void);
static void show_holdings(ActionMenu *menu) {
  if (s_cached_only) {
    set_state("PHONE_OFFLINE");
    show_info(menu);
    return;
  }
  if (!s_list)
    return;
  menu_layer_set_selected_index(s_menu, MenuIndex(0, 0), MenuRowAlignTop,
                                false);
  action_menu_set_result_window(menu, s_list);
}
static void action_callback(ActionMenu *menu, const ActionMenuItem *item,
                            void *context) {
  int action = (int)(intptr_t)action_menu_item_get_action_data(item);
  if (action == 0)
    show_holdings(menu);
  if (action == 1)
    request(0, s_data.page);
  if (action == 2) {
    request(1, 0);
  }
  if (action == 3) {
    if (s_local_hide)
      s_local_hide = false;
    else if (s_data.summary.hide)
      request(2, s_data.page);
    else
      s_local_hide = true;
    persist_write_bool(CACHE_KEY + 1, s_local_hide);
    if (hidden() && window_stack_contains_window(s_detail))
      window_stack_remove(s_detail, false);
    if (hidden() && window_stack_contains_window(s_info))
      window_stack_remove(s_info, false);
    redraw();
  }
  if (action == 4) {
    show_info(menu);
  }
}
static void actions_closed(ActionMenu *menu, const ActionMenuItem *item,
                           void *context) {
  s_action_menu = NULL;
  action_menu_hierarchy_destroy(s_actions, NULL, NULL);
  s_actions = NULL;
}
static void show_actions(void) {
  if (s_action_menu)
    return;
  s_actions = action_menu_level_create(5);
  action_menu_level_add_action(s_actions, "Holdings", action_callback,
                               (void *)0);
  action_menu_level_add_action(s_actions, "Refresh", action_callback,
                               (void *)1);
  action_menu_level_add_action(s_actions, "Next account", action_callback,
                               (void *)2);
  action_menu_level_add_action(s_actions, "Hide / show", action_callback,
                               (void *)3);
  action_menu_level_add_action(s_actions, "Info / connect", action_callback,
                               (void *)4);
  ActionMenuConfig cfg = {
      .root_level = s_actions,
      .colors = {.background = GColorBlack, .foreground = GColorWhite},
      .did_close = actions_closed};
  s_action_menu = action_menu_open(&cfg);
}
static void select_click(ClickRecognizerRef r, void *ctx) { show_actions(); }
static void card_click(ClickRecognizerRef r, void *ctx) {
  s_card = !s_card;
  redraw();
}
static void root_click_config(void *ctx) {
  window_single_click_subscribe(BUTTON_ID_SELECT, select_click);
  window_single_click_subscribe(BUTTON_ID_UP, card_click);
  window_single_click_subscribe(BUTTON_ID_DOWN, card_click);
}
static uint16_t menu_rows(MenuLayer *menu, uint16_t section, void *ctx) {
  return s_data.count + 3;
}
static int16_t menu_height(MenuLayer *menu, MenuIndex *idx, void *ctx) {
  return idx->row < s_data.count ? 66 : 46;
}
static void menu_draw(GContext *ctx, const Layer *cell, MenuIndex *idx,
                      void *context) {
  int i = idx->row;
  GRect b = layer_get_bounds(cell);
  if (i < s_data.count) {
    Holding *row = &s_data.holdings[i];
    draw_text(ctx, row->ticker, FONT_KEY_GOTHIC_24_BOLD,
              GRect(5, -3, b.size.w - 10, 30), GTextAlignmentLeft);
    draw_text(ctx, hidden() ? "Hidden" : row->value, FONT_KEY_GOTHIC_18_BOLD,
              GRect(5, 23, b.size.w - 10, 23), GTextAlignmentLeft);
    draw_text(ctx, row->daily, FONT_KEY_GOTHIC_18,
              GRect(5, 42, b.size.w - 10, 23), GTextAlignmentLeft);
  } else {
    int item = i - s_data.count;
    if (item == 0)
      menu_cell_basic_draw(
          ctx, cell, s_data.page ? "Previous page" : "First page",
          s_data.count ? "Sorted by value" : "No equity holdings", NULL);
    if (item == 1)
      menu_cell_basic_draw(
          ctx, cell, s_data.page + 1 < s_data.pages ? "Next page" : "Last page",
          NULL, NULL);
    if (item == 2)
      menu_cell_basic_draw(ctx, cell, "Options", "Refresh / account", NULL);
  }
}
static void menu_selected(MenuLayer *menu, MenuIndex *idx, void *ctx) {
  if (idx->row < s_data.count) {
    s_selected = idx->row;
    update_detail();
    scroll_layer_set_content_offset(s_detail_scroll, GPointZero, false);
    window_stack_push(s_detail, true);
  } else if (idx->row == s_data.count && s_data.page)
    request(0, s_data.page - 1);
  else if (idx->row == s_data.count + 1 && s_data.page + 1 < s_data.pages)
    request(0, s_data.page + 1);
  else if (idx->row == s_data.count + 2)
    show_actions();
}
static void show_info(ActionMenu *menu) {
  char age[40];
  age_text(age, sizeof(age));
  time_t stamp = s_data.summary.updated;
  struct tm *tm = localtime(&stamp);
  char date[40];
  strftime(date, sizeof(date), "%b %d %H:%M", tm);
  snprintf(s_info_buffer, sizeof(s_info_buffer),
           "%s\n\n%s\n%s (watch time)\n\n%s\n\n%s\n\nConnect / reconnect\nOpen "
           "Pebble Hood settings in the phone app. Pair with your private "
           "backend.\n\nUp / Down: scroll\nBack: return\n\nUSD. Stock daily "
           "change is price movement; investment return compares the position "
           "to its cost basis.\n\n%s",
           s_state[0] ? state_label() : "Portfolio information",
           s_data.summary.valid ? age : "No saved data",
           s_data.summary.valid ? date : "--", s_data.chart_label,
           hidden() ? "Balances hidden" : s_data.note,
           s_data.summary.demo
               ? "DEMO: all values are synthetic. No account is connected."
               : "Official live data requires verified response mapping. No "
                 "trades are available.");
  text_layer_set_text(s_info_text, s_info_buffer);
  GSize size = text_layer_get_content_size(s_info_text);
  scroll_layer_set_content_size(s_info_scroll, GSize(size.w, size.h + 14));
  scroll_layer_set_content_offset(s_info_scroll, GPointZero, false);
  if (menu)
    action_menu_set_result_window(menu, s_info);
  else if (!window_stack_contains_window(s_info))
    window_stack_push(s_info, true);
}
static bool get_int(DictionaryIterator *iter, uint32_t key, uint32_t *out) {
  Tuple *t = dict_find(iter, key);
  if (!t || (t->type != TUPLE_UINT && t->type != TUPLE_INT) ||
      (t->length != 1 && t->length != 2 && t->length != 4))
    return false;
  *out = t->length == 1   ? t->value->uint8
         : t->length == 2 ? t->value->uint16
                          : t->value->uint32;
  return true;
}
static bool get_string(DictionaryIterator *iter, uint32_t key, char *out,
                       size_t max) {
  Tuple *t = dict_find(iter, key);
  if (!t || t->type != TUPLE_CSTRING || !t->length || t->length > max ||
      ((char *)t->value)[t->length - 1])
    return false;
  memcpy(out, t->value->cstring, t->length);
  return true;
}
static void clear_data(void) {
  memset(&s_data, 0, sizeof(s_data));
  memset(&s_pending, 0, sizeof(s_pending));
  s_receiving = false;
  s_cached_only = false;
  persist_delete(CACHE_KEY);
  s_detail_buffer[0] = 0;
  s_info_buffer[0] = 0;
  if (s_detail_text)
    text_layer_set_text(s_detail_text, "");
  if (s_info_text)
    text_layer_set_text(s_info_text, "");
  // Keep the root window on the stack: popping it schedules app termination.
  if (s_action_menu)
    action_menu_close(s_action_menu, false);
  if (window_stack_contains_window(s_detail))
    window_stack_remove(s_detail, false);
  if (window_stack_contains_window(s_info))
    window_stack_remove(s_info, false);
  if (window_stack_contains_window(s_list))
    window_stack_remove(s_list, false);
  s_card = 0;
  redraw();
}
static void inbox(DictionaryIterator *iter, void *context) {
  uint32_t type = 0, g = 0, n = 0;
  get_int(iter, MESSAGE_KEY_TYPE, &type);
  if (type == 5) {
    stop_loading();
    clear_data();
    set_state("SETUP");
    return;
  }
  if (type == 4) {
    stop_loading();
    s_receiving = false;
    if (!get_string(iter, MESSAGE_KEY_ERROR, s_state, sizeof(s_state)))
      set_state("PROVIDER_FAILURE");
    redraw();
    return;
  }
  if (!get_int(iter, MESSAGE_KEY_GEN, &g))
    return;
  if (type == 1) {
    memset(&s_pending, 0, sizeof(s_pending));
    s_receiving = false;
    s_pending.generation = g;
    if (!get_int(iter, MESSAGE_KEY_VERSION, &n) || n != 1)
      return;
    if (!get_int(iter, MESSAGE_KEY_COUNT, &n) || n > ROWS)
      return;
    s_pending.count = n;
    if (!get_int(iter, MESSAGE_KEY_PAGE, &n) || n > 166)
      return;
    s_pending.page = n;
    if (!get_int(iter, MESSAGE_KEY_PAGES, &n) || n < 1 || n > 167)
      return;
    s_pending.pages = n;
    if (s_pending.page >= s_pending.pages)
      return;
    if (!get_int(iter, MESSAGE_KEY_TOTAL_COUNT, &n) || n > 1000)
      return;
    s_pending.total_count = n;
    if (!get_int(iter, MESSAGE_KEY_UPDATED, &n))
      return;
    s_pending.summary.updated = n;
    if (!get_string(iter, MESSAGE_KEY_ACCOUNT, s_pending.summary.account,
                    sizeof(s_pending.summary.account)) ||
        !get_string(iter, MESSAGE_KEY_VALUE, s_pending.summary.value,
                    sizeof(s_pending.summary.value)) ||
        !get_string(iter, MESSAGE_KEY_RETURN, s_pending.summary.change,
                    sizeof(s_pending.summary.change)) ||
        !get_string(iter, MESSAGE_KEY_PERCENT, s_pending.summary.percent,
                    sizeof(s_pending.summary.percent)))
      return;
    get_int(iter, MESSAGE_KEY_DEMO, &n);
    s_pending.summary.demo = n != 0;
    get_int(iter, MESSAGE_KEY_HIDE, &n);
    s_pending.summary.hide = n != 0;
    get_string(iter, MESSAGE_KEY_NOTE, s_pending.note, sizeof(s_pending.note));
    get_string(iter, MESSAGE_KEY_CHART_LABEL, s_pending.chart_label,
               sizeof(s_pending.chart_label));
    get_string(iter, MESSAGE_KEY_ERROR, s_pending.error,
               sizeof(s_pending.error));
    Tuple *chart = dict_find(iter, MESSAGE_KEY_CHART);
    if (chart && chart->type == TUPLE_BYTE_ARRAY && chart->length <= 24) {
      bool valid = chart->length > 1;
      for (int i = 0; i < chart->length; i++)
        if (((uint8_t *)chart->value)[i] > 100)
          valid = false;
      if (valid) {
        s_pending.chart_count = chart->length;
        memcpy(s_pending.chart, chart->value->data, chart->length);
      }
    }
    s_receiving = true;
    if (!s_timeout)
      s_timeout = app_timer_register(22000, timeout, NULL);
  } else if (type == 2 && s_receiving && g == s_pending.generation) {
    if (!get_int(iter, MESSAGE_KEY_INDEX, &n) || n >= s_pending.count)
      return;
    Holding *r = &s_pending.holdings[n];
    if (!get_string(iter, MESSAGE_KEY_TICKER, r->ticker, sizeof(r->ticker)) ||
        !get_string(iter, MESSAGE_KEY_POSITION, r->value, sizeof(r->value)) ||
        !get_string(iter, MESSAGE_KEY_DAILY, r->daily, sizeof(r->daily)) ||
        !get_string(iter, MESSAGE_KEY_DETAIL, r->detail, sizeof(r->detail)))
      return;
    s_pending.received |= 1 << n;
  } else if (type == 3 && s_receiving && g == s_pending.generation) {
    if (s_pending.received != ((1 << s_pending.count) - 1))
      return;
    s_data = s_pending;
    s_data.summary.valid = true;
    s_data.summary.version = CACHE_VERSION;
    s_cached_only = false;
    s_receiving = false;
    stop_loading();
    snprintf(s_state, sizeof(s_state), "%s", s_data.error);
    persist_write_data(CACHE_KEY, &s_data.summary, sizeof(Summary));
    // Any open detail belongs to the previous snapshot: return to the refreshed
    // list.
    if (window_stack_contains_window(s_detail))
      window_stack_remove(s_detail, false);
    if (s_menu)
      menu_layer_set_selected_index(s_menu, MenuIndex(0, 0), MenuRowAlignTop,
                                    false);
    redraw();
  }
}
static void inbox_dropped(AppMessageResult reason, void *ctx) {
  stop_loading();
  s_receiving = false;
  set_state("TRANSFER_FAILED");
}
static void outbox_failed(DictionaryIterator *iter, AppMessageResult reason,
                          void *ctx) {
  stop_loading();
  set_state("PHONE_OFFLINE");
}
static void connection(bool connected) {
  if (!connected) {
    stop_loading();
    set_state("PHONE_OFFLINE");
  } else
    request(0, s_data.page);
}
static void tick(struct tm *time, TimeUnits units) { redraw(); }
static void make_scroll(Window **window, ScrollLayer **scroll,
                        TextLayer **text) {
  *window = window_create();
  Layer *root = window_get_root_layer(*window);
  GRect b = layer_get_bounds(root);
  *scroll = scroll_layer_create(b);
  *text = text_layer_create(GRect(7, 0, b.size.w - 14, 2000));
  text_layer_set_font(*text, fonts_get_system_font(FONT_KEY_GOTHIC_18));
  text_layer_set_text_color(*text, GColorBlack);
  text_layer_set_background_color(*text, GColorWhite);
  text_layer_set_overflow_mode(*text, GTextOverflowModeWordWrap);
  scroll_layer_add_child(*scroll, text_layer_get_layer(*text));
  layer_add_child(root, scroll_layer_get_layer(*scroll));
  scroll_layer_set_click_config_onto_window(*scroll, *window);
}
static void init(void) {
  s_local_hide = persist_read_bool(CACHE_KEY + 1);
  s_main = window_create();
  Layer *root = window_get_root_layer(s_main);
  GRect b = layer_get_bounds(root);
  s_bar = status_bar_layer_create();
  status_bar_layer_set_colors(s_bar, GColorWhite, GColorBlack);
  layer_add_child(root, status_bar_layer_get_layer(s_bar));
  s_canvas = layer_create(GRect(0, STATUS_BAR_LAYER_HEIGHT, b.size.w,
                                b.size.h - STATUS_BAR_LAYER_HEIGHT));
  layer_set_update_proc(s_canvas, canvas_update);
  layer_add_child(root, s_canvas);
  window_set_click_config_provider(s_main, root_click_config);
  s_list = window_create();
  GRect lb = layer_get_bounds(window_get_root_layer(s_list));
  s_list_status = text_layer_create(GRect(5, 0, lb.size.w - 10, 36));
  text_layer_set_font(s_list_status, fonts_get_system_font(FONT_KEY_GOTHIC_14));
  layer_add_child(window_get_root_layer(s_list),
                  text_layer_get_layer(s_list_status));
  s_menu = menu_layer_create(GRect(0, 36, lb.size.w, lb.size.h - 36));
  menu_layer_set_callbacks(s_menu, NULL,
                           (MenuLayerCallbacks){.get_num_rows = menu_rows,
                                                .get_cell_height = menu_height,
                                                .draw_row = menu_draw,
                                                .select_click = menu_selected});
  menu_layer_set_click_config_onto_window(s_menu, s_list);
  layer_add_child(window_get_root_layer(s_list), menu_layer_get_layer(s_menu));
  make_scroll(&s_detail, &s_detail_scroll, &s_detail_text);
  make_scroll(&s_info, &s_info_scroll, &s_info_text);
  if (persist_read_data(CACHE_KEY, &s_data.summary, sizeof(Summary)) ==
          sizeof(Summary) &&
      s_data.summary.version == CACHE_VERSION && s_data.summary.valid) {
    s_cached_only = true;
    snprintf(s_state, sizeof(s_state), "STALE");
  } else {
    memset(&s_data, 0, sizeof(s_data));
    snprintf(s_state, sizeof(s_state), "SETUP");
  }
  app_message_register_inbox_received(inbox);
  app_message_register_inbox_dropped(inbox_dropped);
  app_message_register_outbox_failed(outbox_failed);
  app_message_open(INBOX, 128);
  connection_service_subscribe(
      (ConnectionHandlers){.pebble_app_connection_handler = connection});
  tick_timer_service_subscribe(MINUTE_UNIT, tick);
  window_stack_push(s_main, true);
  s_loading = true;
  s_timeout = app_timer_register(22000, timeout, NULL);
  s_launch_timer = app_timer_register(600, launch_refresh, NULL);
}
static void deinit(void) {
  if (s_launch_timer)
    app_timer_cancel(s_launch_timer);
  if (s_timeout)
    app_timer_cancel(s_timeout);
  tick_timer_service_unsubscribe();
  connection_service_unsubscribe();
  app_message_deregister_callbacks();
  if (s_action_menu)
    action_menu_close(s_action_menu, false);
  if (s_actions)
    action_menu_hierarchy_destroy(s_actions, NULL, NULL);
  text_layer_destroy(s_info_text);
  scroll_layer_destroy(s_info_scroll);
  window_destroy(s_info);
  text_layer_destroy(s_detail_text);
  scroll_layer_destroy(s_detail_scroll);
  window_destroy(s_detail);
  menu_layer_destroy(s_menu);
  text_layer_destroy(s_list_status);
  window_destroy(s_list);
  layer_destroy(s_canvas);
  status_bar_layer_destroy(s_bar);
  window_destroy(s_main);
}
int main(void) {
  init();
  app_event_loop();
  deinit();
}
