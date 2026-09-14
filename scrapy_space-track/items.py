import scrapy


class GPLatestItem(scrapy.Item):
    norad_id = scrapy.Field()
    intldes = scrapy.Field()
    name = scrapy.Field()
    epoch = scrapy.Field()
    tle1 = scrapy.Field()
    tle2 = scrapy.Field()
    orbit_class = scrapy.Field()
    period = scrapy.Field()
    perigee = scrapy.Field()
    apogee = scrapy.Field()
    semimajor_axis = scrapy.Field()
    eccentricity = scrapy.Field()
    inclination = scrapy.Field()
    raan = scrapy.Field()
    arg_perigee = scrapy.Field()
    mean_anomaly = scrapy.Field()
    rev_at_epoch = scrapy.Field()
    object_type = scrapy.Field()
    rcs_size = scrapy.Field()
    country_code = scrapy.Field()
    launch_date = scrapy.Field()
    launch_site = scrapy.Field()
    decay_date = scrapy.Field()


class HistoryTLEItem(scrapy.Item):
    norad_id = scrapy.Field()
    sate_name = scrapy.Field()
    epoch = scrapy.Field()
    tle1 = scrapy.Field()
    tle2 = scrapy.Field()
    orbit_class = scrapy.Field()
    period = scrapy.Field()
    sate_type = scrapy.Field()
    fixed_lon = scrapy.Field()
    update_time = scrapy.Field()


class SatCatTLEItem(scrapy.Item):
    norad_id = scrapy.Field()
    epoch = scrapy.Field()
    tle1 = scrapy.Field()
    tle2 = scrapy.Field()
    update_time = scrapy.Field()
