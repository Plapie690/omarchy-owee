import QtQuick
import QtTest
import "../.." as Weather

Item {
  id: scene
  width: 800; height: 1200
  readonly property var originalOrder: ["wind", "humidity", "uv", "sun", "pressure", "visibility", "precipitation", "air", "pollen"]
  Weather.WeatherCards {
    id: cards
    x: 20; y: 20; width: 460
    cardInfo: function(id) { return {title: id, value: "24", detail: "Description de la carte"} }
  }
  Flickable {
    id: scroller
    x: 20; y: 880; width: 460; height: 280
    visible: false
    clip: true
    contentHeight: scrollCards.height
    Weather.WeatherCards {
      id: scrollCards
      width: scroller.width
      editing: true
      scrollView: scroller
      cardInfo: function(id) { return {title: id, value: "24", detail: "Carte défilante"} }
    }
  }

  TestCase {
    id: tests
    name: "WeatherCardsPointer"
    when: windowShown
    SignalSpy { id: reordered; target: cards; signalName: "reorderRequested" }
    SignalSpy { id: toggled; target: cards; signalName: "toggleRequested" }
    SignalSpy { id: scrolledOrder; target: scrollCards; signalName: "reorderRequested" }

    function init() {
      cards.cancelDrag()
      cards.order = scene.originalOrder.slice()
      cards.hidden = ["air", "pollen"]
      cards.editing = true
      cards.busy = false
      cards.active = true
      cards.scrollView = null
      cards.LayoutMirroring.enabled = false
      scroller.visible = false
      scroller.contentY = 0
      scrollCards.order = scene.originalOrder.slice()
      scrollCards.cancelDrag()
      scrolledOrder.clear()
      reordered.clear(); toggled.clear()
      wait(20)
    }
    function cleanup() { cards.cancelDrag(); scrollCards.cancelDrag() }
    function control(id) {
      var found = findChild(cards, id)
      verify(found !== null, "Missing control " + id)
      return found
    }
    function point(item, x, y) { return item.mapToItem(cards, x, y) }
    function startDrag(id, targetId) {
      var handle = control("drag-" + id)
      var start = point(handle, handle.width / 2, handle.height / 2)
      var target = control("card-" + targetId)
      var destination = point(target, target.width / 2, target.height / 2)
      mousePress(cards, start.x, start.y, Qt.LeftButton)
      mouseMove(cards, start.x + 12, start.y + 8, 20)
      verify(cards.dragging, "Dragging should start from the handle")
      mouseMove(cards, destination.x, destination.y, 20)
      return destination
    }
    function test_real_pointer_drop_emits_once_and_keeps_source_until_commit() {
      var destination = startDrag("wind", "uv")
      compare(reordered.count, 0)
      compare(cards.order.join(","), scene.originalOrder.join(","))
      compare(cards.targetIndex, 2)
      mouseRelease(cards, destination.x, destination.y, Qt.LeftButton)
      compare(cards.dragging, false)
      compare(reordered.count, 1)
      compare(reordered.signalArguments[0][0].join(","), "humidity,uv,wind,sun,pressure,visibility,precipitation,air,pollen")
    }
    function test_escape_cancels_drag_without_saving() {
      var destination = startDrag("wind", "sun")
      keyClick(Qt.Key_Escape)
      compare(cards.dragging, false)
      mouseRelease(cards, destination.x, destination.y, Qt.LeftButton)
      compare(reordered.count, 0)
      compare(cards.order.join(","), scene.originalOrder.join(","))
    }
    function test_closing_or_disabling_editor_cancels_drag() {
      var destination = startDrag("wind", "sun")
      cards.active = false
      compare(cards.dragging, false)
      mouseRelease(cards, destination.x, destination.y, Qt.LeftButton)
      compare(reordered.count, 0)
    }
    function test_drop_outside_grid_is_cancelled() {
      startDrag("wind", "uv")
      mouseMove(cards, cards.width + 30, 100, 20)
      compare(cards.targetIndex, -1)
      mouseRelease(cards, cards.width + 30, 100, Qt.LeftButton)
      compare(reordered.count, 0)
    }
    function test_small_handle_click_is_not_a_reorder() {
      var handle = control("drag-wind")
      mouseClick(handle, handle.width / 2, handle.height / 2)
      compare(reordered.count, 0)
      compare(cards.dragging, false)
    }
    function test_card_body_does_not_start_drag() {
      var tile = control("card-wind")
      mousePress(tile, 35, 50, Qt.LeftButton)
      mouseMove(tile, 35, 100, 20)
      mouseRelease(tile, 35, 100, Qt.LeftButton)
      compare(cards.dragging, false)
      compare(reordered.count, 0)
    }
    function test_hidden_cards_are_reorderable_only_in_editor() {
      compare(cards.shownOrder.length, 9)
      verify(control("card-air").visible)
      var destination = startDrag("air", "wind")
      mouseRelease(cards, destination.x, destination.y, Qt.LeftButton)
      compare(reordered.count, 1)
      compare(reordered.signalArguments[0][0][0], "air")
      cards.editing = false
      compare(cards.shownOrder.length, 7)
      compare(findChild(cards, "card-air"), null)
    }
    function test_buttons_and_keyboard_provide_non_drag_alternatives() {
      var down = control("down-wind")
      mouseClick(down, down.width / 2, down.height / 2)
      compare(reordered.count, 1)
      compare(reordered.signalArguments[0][0][1], "wind")
      reordered.clear()
      var handle = control("drag-humidity")
      handle.forceActiveFocus()
      keyClick(Qt.Key_Up, Qt.ControlModifier)
      compare(reordered.count, 1)
      compare(reordered.signalArguments[0][0][0], "humidity")
      var toggle = control("toggle-air")
      mouseClick(toggle, toggle.width / 2, toggle.height / 2)
      compare(toggled.count, 1)
      compare(toggled.signalArguments[0][0], "air")
    }
    function test_busy_editor_never_commits() {
      cards.busy = true
      var handle = control("drag-wind")
      mousePress(handle, 15, 15, Qt.LeftButton)
      mouseMove(handle, 120, 120, 20)
      mouseRelease(handle, 120, 120, Qt.LeftButton)
      compare(cards.dragging, false)
      compare(reordered.count, 0)
    }
    function test_rtl_grid_uses_visible_target_column() {
      cards.LayoutMirroring.enabled = true
      compare(control("card-wind").x > control("card-humidity").x, true)
      var destination = startDrag("wind", "humidity")
      compare(cards.targetIndex, 1)
      mouseRelease(cards, destination.x, destination.y, Qt.LeftButton)
      compare(reordered.count, 1)
      compare(reordered.signalArguments[0][0][0], "humidity")
    }
    function test_auto_scroll_reaches_cards_below_viewport() {
      scroller.visible = true
      var handle = findChild(scrollCards, "drag-wind")
      verify(handle !== null)
      var point = handle.mapToItem(scroller, handle.width / 2, handle.height / 2)
      mousePress(scroller, point.x, point.y, Qt.LeftButton)
      mouseMove(scroller, 100, scroller.height - 10, 20)
      verify(scrollCards.dragging)
      tryVerify(function() { return scroller.contentY >= scroller.contentHeight - scroller.height - 1 }, 2500)
      compare(scrollCards.targetIndex, 8)
      compare(scrolledOrder.count, 0)
      mouseRelease(scroller, 100, scroller.height - 10, Qt.LeftButton)
      compare(scrolledOrder.count, 1)
      compare(scrolledOrder.signalArguments[0][0][8], "wind")
    }
    function test_drop_outside_viewport_cancels_even_inside_tall_grid() {
      scroller.visible = true
      var handle = findChild(scrollCards, "drag-wind")
      var point = handle.mapToItem(scroller, handle.width / 2, handle.height / 2)
      mousePress(scroller, point.x, point.y, Qt.LeftButton)
      mouseMove(scroller, 100, scroller.height + 30, 20)
      verify(scrollCards.dragging)
      compare(scrollCards.targetIndex, -1)
      mouseRelease(scroller, 100, scroller.height + 30, Qt.LeftButton)
      compare(scrolledOrder.count, 0)
    }
  }
}
