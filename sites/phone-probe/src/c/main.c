#include <pebble.h>
static Window *window;
static TextLayer *title, *body;
static char summary[200] = "Waiting for phone...\n\nDemo access test only.\nSelect retries.";
static void receive(DictionaryIterator *iter, void *context) {
  Tuple *value = dict_find(iter, MESSAGE_KEY_SUMMARY);
  if(value && value->type == TUPLE_CSTRING && value->length > 0) {
    snprintf(summary, sizeof(summary), "%s", value->value->cstring);
    text_layer_set_text(body, summary);
  }
}
static void select_click(ClickRecognizerRef recognizer, void *context) {
  DictionaryIterator *iter;
  if(app_message_outbox_begin(&iter) == APP_MSG_OK) {
    dict_write_uint8(iter, MESSAGE_KEY_RUN, 1);
    app_message_outbox_send();
    text_layer_set_text(body, "Testing phone access...\n\nDemo only.");
  }
}
static void clicks(void *context) { window_single_click_subscribe(BUTTON_ID_SELECT, select_click); }
static void load(Window *unused) {
  GRect bounds = layer_get_bounds(window_get_root_layer(window));
  title = text_layer_create(GRect(6, 2, bounds.size.w-12, 30));
  text_layer_set_font(title, fonts_get_system_font(FONT_KEY_GOTHIC_24_BOLD));
  text_layer_set_text(title, "Sites test");
  layer_add_child(window_get_root_layer(window), text_layer_get_layer(title));
  body = text_layer_create(GRect(6, 35, bounds.size.w-12, bounds.size.h-37));
  text_layer_set_font(body, fonts_get_system_font(FONT_KEY_GOTHIC_18));
  text_layer_set_text(body, summary);
  layer_add_child(window_get_root_layer(window), text_layer_get_layer(body));
}
static void unload(Window *unused) { text_layer_destroy(title); text_layer_destroy(body); }
int main(void) {
  window = window_create();
  window_set_window_handlers(window, (WindowHandlers){.load=load,.unload=unload});
  window_set_click_config_provider(window, clicks);
  app_message_register_inbox_received(receive);
  app_message_open(256, 64);
  window_stack_push(window, false);
  app_event_loop();
  window_destroy(window);
}
