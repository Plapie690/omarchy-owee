import QtQuick
import qs.Commons as Commons

QtObject {
  id: root
  property string mode: "english"
  // The default follows live Omarchy changes; isolated QA can inject a locale.
  property string systemLocaleName: Commons.I18n.formatLocale
  readonly property var locale: Qt.locale(mode === "system" ? systemLocaleName : "en_GB")

  function number(value, decimals) {
    if (typeof value !== "number" || !isFinite(value)) return "—"
    var places = decimals === undefined ? 0 : Math.max(0, Math.min(6, Math.round(decimals)))
    return value.toLocaleString(locale, "f", places)
  }
  function digits(value, width) {
    var text = number(value, 0).split(locale.groupSeparator).join("")
    var zero = number(0, 0)
    while (text.length < width) text = zero + text
    return text
  }
  function dateParts(value) {
    if (typeof value !== "string") return null
    var match = /^(\d{4})-(\d{2})-(\d{2})(?:T|$)/.exec(value)
    if (!match) return null
    var year = Number(match[1]), month = Number(match[2]), day = Number(match[3])
    var date = new Date(Date.UTC(year, month - 1, day))
    if (year < 1970 || year > 2200 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null
    return {year: year, month: month, day: day, weekday: date.getUTCDay() || 7}
  }
  function datePattern(parts, pattern) {
    return pattern.replace(/'([^']|'')*'|yyyy|yy|MMMM|MMM|MM|M|dddd|ddd|dd|d/g, function(token) {
      if (token[0] === "'") return token.slice(1, -1).replace(/''/g, "'")
      if (token === "yyyy") return digits(parts.year, 4)
      if (token === "yy") return digits(parts.year % 100, 2)
      if (token === "MMMM") return locale.monthName(parts.month - 1, Locale.LongFormat)
      if (token === "MMM") return locale.monthName(parts.month - 1, Locale.ShortFormat)
      if (token === "dddd") return locale.dayName(parts.weekday, Locale.LongFormat)
      if (token === "ddd") return locale.dayName(parts.weekday, Locale.ShortFormat)
      if (token === "MM" || token === "M") return digits(parts.month, token.length)
      return digits(parts.day, token.length)
    })
  }
  function day(value) {
    var parts = dateParts(value)
    return parts ? datePattern(parts, mode === "system" ? locale.dateFormat(Locale.ShortFormat) : "ddd d MMM") : "—"
  }
  function timeParts(hour, minute) {
    var pattern = mode === "system" ? locale.timeFormat(Locale.ShortFormat) : "HH:mm"
    var twelve = /AP|Ap|aP|ap/.test(pattern)
    return pattern.replace(/'([^']|'')*'|AP|Ap|aP|ap|HH|hh|H|h|mm|m|ss|s|t+/g, function(token) {
      if (token[0] === "'") return token.slice(1, -1).replace(/''/g, "'")
      if (/^[aA][pP]$/.test(token)) {
        var period = hour < 12 ? locale.amText : locale.pmText
        return token === "ap" ? period.toLowerCase() : token === "AP" ? period.toUpperCase() : period
      }
      if (token[0] === "H") return digits(hour, token.length)
      if (token[0] === "h") return digits(twelve ? hour % 12 || 12 : hour, token.length)
      if (token[0] === "m") return digits(minute, token.length)
      if (token[0] === "s") return digits(0, token.length)
      return "" // A timezone token cannot describe a clock label without its zone.
    }).trim()
  }
  function cityTime(value) {
    // These fields already describe the selected city. Never parse as desktop time.
    if (!dateParts(value)) return "—"
    var match = /T(\d{2}):(\d{2})(?::(\d{2}))?(?:Z|[+-]\d{2}:\d{2})?$/.exec(value)
    if (!match || Number(match[1]) > 23 || Number(match[2]) > 59 || (match[3] !== undefined && Number(match[3]) > 59)) return "—"
    return timeParts(Number(match[1]), Number(match[2]))
  }
  function clockHour(hour) {
    if (typeof hour !== "number" || !isFinite(hour) || hour < 0 || hour > 24 || Math.round(hour) !== hour) return "—"
    return hour === 24 ? "24:00" : timeParts(hour, 0)
  }
  function dayTime(value) {
    var parts = dateParts(value), clock = cityTime(value)
    return parts && clock !== "—" ? datePattern(parts, mode === "system" ? locale.dateFormat(Locale.ShortFormat) : "dd/MM") + " " + clock : "—"
  }
  function instant(epoch) {
    if (typeof epoch !== "number" || !isFinite(epoch) || epoch < 0 || epoch > 7258118400) return "—"
    var date = new Date(epoch * 1000)
    return date.toLocaleString(locale, mode === "system" ? locale.dateTimeFormat(Locale.ShortFormat) : "dd/MM hh:mm")
  }
}
