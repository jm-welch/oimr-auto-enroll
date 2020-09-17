-- table to hold logged events for regfox-google classrooom Bridge
create table oimr_logging
(
    recno     int          not null
        primary key,
    log_level varchar(24)  null,
    module    varchar(50)  null,
    method    varchar(50)  null,
    line_num  int          null,
    mess_date datetime     null,
    message   varchar(500) null
);