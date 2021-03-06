#!/usr/bin/env python
# -*- coding:utf-8 -*-
import os
default_config = """#!/bin/sh

# Event script for ctdb-specific setup and other things that don't fit
# elsewhere.

[ -n "$CTDB_BASE" ] || CTDB_BASE=$(d=$(dirname "$0") ; cd -P "$d" ; dirname "$PWD")

. "${CTDB_BASE}/functions"

loadconfig

############################################################

# type is commonly supported and more portable than which(1)
# shellcheck disable=SC2039
select_tdb_checker ()
{
    # Find the best TDB consistency check available.
    use_tdb_tool_check=false
    type tdbtool >/dev/null 2>&1 && found_tdbtool=true
    type tdbdump >/dev/null 2>&1 && found_tdbdump=true

    if $found_tdbtool && echo "help" | tdbtool | grep -q check ; then
            use_tdb_tool_check=true
    elif $found_tdbtool && $found_tdbdump ; then
            cat <<EOF
WARNING: The installed 'tdbtool' does not offer the 'check' subcommand.
 Using 'tdbdump' for database checks.
 Consider updating 'tdbtool' for better checks!
EOF
    elif $found_tdbdump ; then
        cat <<EOF
WARNING: 'tdbtool' is not available.
 Using 'tdbdump' to check the databases.
 Consider installing a recent 'tdbtool' for better checks!
EOF
    else
        cat <<EOF
WARNING: Cannot check databases since neither
 'tdbdump' nor 'tdbtool check' is available.
 Consider installing tdbtool or at least tdbdump!
EOF
        return 1
    fi
}

check_tdb ()
{
    _db="$1"

    if $use_tdb_tool_check ; then
        # tdbtool always exits with 0  :-(
        if timeout 10 tdbtool "$_db" check 2>/dev/null |
            grep -q "Database integrity is OK" ; then
            return 0
        else
            return 1
        fi
    else
        timeout 10 tdbdump "$_db" >/dev/null 2>/dev/null
        return $?
    fi
}

check_persistent_databases ()
{
    _dir="${CTDB_DBDIR_PERSISTENT:-${CTDB_DBDIR:-${CTDB_VARDIR}}/persistent}"
    [ -d "$_dir" ] || return 0

    [ "${CTDB_MAX_PERSISTENT_CHECK_ERRORS:-0}" = "0" ] || return 0

    for _db in "$_dir/"*.tdb.*[0-9] ; do
        [ -r "$_db" ] || continue
        check_tdb "$_db" || die "Persistent database $_db is corrupted! CTDB will not start."
    done
}

check_non_persistent_databases ()
{
    _dir="${CTDB_DBDIR:-${CTDB_VARDIR}}"
    [ -d "$_dir" ] || return 0

    for _db in "${_dir}/"*.tdb.*[0-9] ; do
        [ -r "$_db" ] || continue
        check_tdb "$_db" || {
            _backup="${_db}.$(date +'%Y%m%d.%H%M%S.%N').corrupt"
            cat <<EOF
WARNING: database ${_db} is corrupted.
 Moving to backup ${_backup} for later analysis.
EOF
            mv "$_db" "$_backup"

            # Now remove excess backups
            _max="${CTDB_MAX_CORRUPT_DB_BACKUPS:-10}"
            _bdb="${_db##*/}" # basename
            find "$_dir" -name "${_bdb}.*.corrupt" |
                    sort -r |
                    tail -n +$((_max + 1)) |
                    xargs rm -f
        }
    done
}

set_ctdb_variables ()
{
    # set any tunables from the config file
    set | sed -n '/^CTDB_SET_/s/=.*//p' |
    while read v; do
        varname="${v#CTDB_SET_}"
        value=$(eval echo "\$$v")
        if $CTDB setvar "$varname" "$value" ; then
            echo "Set $varname to $value"
        else
            echo "Invalid configuration: CTDB_SET_${varname}=${value}"
            return 1
        fi
    done
}

############################################################

ctdb_check_args "$@"

case "$1" in
init)
        # make sure we have a blank state directory for the scripts to work with
        rm -rf "$CTDB_SCRIPT_VARDIR"
        mkdir -p "$CTDB_SCRIPT_VARDIR" || die "mkdir -p ${CTDB_SCRIPT_VARDIR} - failed - $?" $?
  
        if select_tdb_checker ; then
            check_persistent_databases || exit $?
            check_non_persistent_databases
        fi
        ;;

setup)
        # Set any tunables from the config file
        set_ctdb_variables || die "Aborting setup due to invalid configuration - fix typos, remove unknown tunables"
        ;;

startup)
        $CTDB attach ctdb.tdb persistent
        ;;
esac

# all OK
exit 0
"""
ctdb_path = "/usr/local/samba/etc/ctdb/"
def write_content():
    with open(ctdb_path+"env.header",mode="w") as fw:
        fw.write("export PATH=$PATH:/usr/local/samba/bin/")
        
def check_env():
    if os.path.exists(ctdb_path+"env.header"):
        os.system("rm -rf %s+env.header" %ctdb_path)
        write_content()
    else:
        write_content()
    content = os.popen("cat /usr/local/samba/etc/ctdb/env.header").read()
    if content == "export PATH=$PATH:/usr/local/samba/bin/":
        print "The content is right now!"

def update_ctdb_cfg():
    keyword = '. "${CTDB_BASE}/functions"'
    if os.path.exists(ctdb_path+"events.d/00.ctdb"):
        with open(ctdb_path+"events.d/00.ctdb") as fr:
            content = fr.read()
            post = content.find(keyword)
            if post != -1:
                content = content[:post+len(keyword)]+"\n" +'. "${CTDB_BASE}/env.header"' + content[post +len(keyword):]
                file = open(ctdb_path+"events.d/00.ctdb",'w')
                file.write(content)
                
if __name__=="__main__":
    write_content()
    check_env()
    with open(ctdb_path+"events.d/00.ctdb",mode="w") as fw:
        fw.write(default_config)
    update_ctdb_cfg()
