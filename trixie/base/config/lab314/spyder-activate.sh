# Conda and Micromamba source this only when activating /opt/lab314.
case ":${PATH-}:" in
    *:/usr/local/lib/rpi-images/lab314-bin:*) ;;
    *)
        export PATH="/usr/local/lib/rpi-images/lab314-bin${PATH+:$PATH}"
        _RPI_LAB314_SPYDER_PATH=1
        ;;
esac
