# Remove only the directory added by our activation hook.
if [ "${_RPI_LAB314_SPYDER_PATH-}" = 1 ]; then
    case "${PATH-}" in
        /usr/local/lib/rpi-images/lab314-bin:*) export PATH="${PATH#*:}" ;;
        /usr/local/lib/rpi-images/lab314-bin) export PATH= ;;
        *:/usr/local/lib/rpi-images/lab314-bin:*)
            _rpi_left=${PATH%%:/usr/local/lib/rpi-images/lab314-bin:*}
            _rpi_right=${PATH#*:/usr/local/lib/rpi-images/lab314-bin:}
            export PATH="$_rpi_left:$_rpi_right"
            unset _rpi_left _rpi_right
            ;;
        *:/usr/local/lib/rpi-images/lab314-bin)
            export PATH="${PATH%:/usr/local/lib/rpi-images/lab314-bin}"
            ;;
    esac
    unset _RPI_LAB314_SPYDER_PATH
fi
