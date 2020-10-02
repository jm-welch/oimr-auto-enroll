-- table to hold logged events for regfox<->google classrooom Bridge
drop table oimr_logging;

create table oimr_logging
(
    recno     int          NOT NULL AUTO_INCREMENT,
    log_level varchar(24)  null,
    module    varchar(50)  null,
    method    varchar(50)  null,
    line_num  int          null,
    mess_date datetime     null,
    message   varchar(500) null
);