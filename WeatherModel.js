.pragma library

// WMO codes supplied by the existing forecast provider. Unknown is not sunny.
function family(code) {
    if (typeof code !== "number" || !isFinite(code)) return "unknown";
    if (code === 0) return "clear";
    if (code === 1) return "mostlyClear";
    if (code === 2) return "partlyCloudy";
    if (code === 3) return "cloudy";
    if (code === 45 || code === 48) return "fog";
    if ([51,53,55,56,57,61,63,65,66,67,80,81,82].indexOf(code) >= 0) return "rain";
    if ([71,73,75,77,85,86].indexOf(code) >= 0) return "snow";
    if ([95,96,99].indexOf(code) >= 0) return "storm";
    return "unknown";
}

function description(code) {
    var names = {clear:"Clear sky", mostlyClear:"Mostly clear", partlyCloudy:"Partly cloudy",
        cloudy:"Overcast", fog:"Fog", rain:"Rain", snow:"Snow", storm:"Thunderstorms", unknown:"Weather unavailable"};
    return names[family(code)];
}

function dayLabel(stamp, reference, stale) {
    var date = new Date(stamp + "T12:00:00");
    if (!isFinite(date.getTime())) return "Date unavailable";
    if (!stale && reference) {
        if (stamp === reference) return "Today";
        var next = new Date(reference + "T12:00:00");
        next.setDate(next.getDate()+1);
        if (date.getFullYear() === next.getFullYear() && date.getMonth() === next.getMonth() && date.getDate() === next.getDate()) return "Tomorrow";
    }
    return Qt.locale("en_GB").toString(date, "ddd d MMM");
}

// Provider's European AQI bands: https://open-meteo.com/en/docs/air-quality-api
function airCategory(value) {
    if (typeof value !== "number" || !isFinite(value) || value < 0) return "Unavailable";
    if (value <= 20) return "Good";
    if (value <= 40) return "Fair";
    if (value <= 60) return "Moderate";
    if (value <= 80) return "Poor";
    if (value <= 100) return "Very poor";
    return "Extremely poor";
}

function windOrigin(value) {
    if (typeof value !== "number" || !isFinite(value)) return "Direction unavailable";
    var bearings = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    return "From " + bearings[Math.round(((value%360)+360)%360/45)%8] + " · " + Math.round(value) + "°";
}

function explanation(kind) {
    var descriptions = {
        wind:"Wind speed now. The direction tells you where the wind comes from.",
        humidity:"Relative humidity now: how much water vapour the air holds compared with its capacity at this temperature.",
        uv:"The highest UV index forecast for today, rather than the UV level right now.",
        sun:"Sunrise and sunset in this city's local time, to plan around daylight.",
        pressure:"Air pressure at ground level, in hectopascals. One reading alone does not predict a change in weather.",
        visibility:"Forecast distance you can see through the air. Fog and other conditions can reduce it.",
        precipitation:"Recent rain and snow amount in millimetres over the last reported interval. This is an amount, rather than a probability.",
        air:"European air quality index from CAMS. Higher values mean more pollution. Categories follow the Open-Meteo scale.",
        pollen:"Highest available pollen concentration, in grains per cubic metre. This is a forecast, rather than a personal allergy rating. Coverage varies by region."
    };
    return descriptions[kind] || "";
}

function clock(hour) {
    return (hour < 10 ? "0" : "") + hour + ":00";
}

// Open-Meteo probabilities cover the preceding hour: 01:00 means 00:00–01:00.
// UTC arithmetic here only shifts city-local calendar labels, not timezones.
function rainInterval(stamp) {
    if (typeof stamp !== "string") return null;
    var parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):00(?::00)?$/.exec(stamp);
    if (!parts) return null;
    var year=Number(parts[1]), month=Number(parts[2]), day=Number(parts[3]), hour=Number(parts[4]);
    var end=new Date(Date.UTC(year,month-1,day,hour));
    if (hour>23 || end.getUTCFullYear()!==year || end.getUTCMonth()!==month-1 || end.getUTCDate()!==day) return null;
    var start=new Date(end.getTime()-3600000), startHour=start.getUTCHours();
    var date=start.getUTCFullYear()+"-"+("0"+(start.getUTCMonth()+1)).slice(-2)+"-"+("0"+start.getUTCDate()).slice(-2);
    return {date:date, hour:startHour, label:clock(startHour)+"–"+clock(startHour+1)};
}

function rainHours(hourly) {
    var days={};
    if (hourly && Array.isArray(hourly.rain_intervals)) {
        hourly.rain_intervals.forEach(function(interval){
            if(!interval || typeof interval.date!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(interval.date) || typeof interval.hour!=="number" || interval.hour%1!==0 || interval.hour<0 || interval.hour>23)return;
            if(!days[interval.date])days[interval.date]=new Array(24).fill(null);
            var p=interval.probability;
            if(typeof p!=="number"||!isFinite(p))return;
            var old=days[interval.date][interval.hour];
            days[interval.date][interval.hour]=old===null?p:Math.max(old,p);
        });
        return days;
    }
    if (!hourly || !Array.isArray(hourly.time) || !Array.isArray(hourly.precipitation_probability)) return days;
    for (var i=0;i<Math.min(hourly.time.length,500);i++) {
        var interval=rainInterval(hourly.time[i]);
        if (!interval) continue;
        if (!days[interval.date]) days[interval.date]=new Array(24).fill(null);
        var chance=hourly.precipitation_probability[i];
        if (typeof chance!=="number" || !isFinite(chance)) continue;
        chance=Math.max(0,Math.min(100,Math.round(chance)));
        // When a local clock hour repeats, keep its highest available chance.
        var previous=days[interval.date][interval.hour];
        days[interval.date][interval.hour]=previous===null?chance:Math.max(previous,chance);
    }
    return days;
}

function rainDetails(hourly) {
    var days={};
    if(!hourly || !Array.isArray(hourly.rain_intervals))return days;
    hourly.rain_intervals.forEach(function(interval){
        if(!interval || typeof interval.date!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(interval.date) || typeof interval.hour!=="number" || interval.hour%1!==0 || interval.hour<0 || interval.hour>23)return;
        if(!days[interval.date])days[interval.date]=Array.from({length:24},function(){return []});
        days[interval.date][interval.hour].push(interval);
        var end=String(interval.end_local), hour=Number(end.slice(11,13));
        if(end.slice(0,10)===interval.date && end.slice(14,16)==="00" && String(interval.start_local).slice(14,16)==="00")
            for(var h=interval.hour+1;h<hour;h++)days[interval.date][h].push({clock_gap:true});
    });
    return days;
}

function offsetLabel(seconds) {
    var n=Math.abs(seconds),hours=Math.floor(n/3600),minutes=Math.floor(n%3600/60);
    return "UTC"+(seconds<0?"−":"+")+("0"+hours).slice(-2)+":"+("0"+minutes).slice(-2);
}
