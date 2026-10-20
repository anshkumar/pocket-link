#!/bin/bash
# Builds PocketLinkTest.apk with plain SDK tools (no Gradle needed).
# Needs: JDK 8+, Android platform android.jar (API 23+), aapt, dx (or d8), zipalign, apksigner.
# Debian/Ubuntu: sudo apt install android-sdk android-sdk-platform-23 dalvik-exchange apksigner
set -euo pipefail
cd "$(dirname "$0")"
SDK=${ANDROID_SDK:-/usr/lib/android-sdk}
JAR=${ANDROID_JAR:-$(ls -d $SDK/platforms/android-*/android.jar | sort -V | tail -1)}
rm -rf build && mkdir -p build/gen build/classes build/dex
aapt package -f -m -J build/gen -M AndroidManifest.xml -S res -I "$JAR" -F build/app.unsigned.apk
javac -encoding UTF-8 -source 8 -target 8 -Xlint:-options -bootclasspath "$JAR" -d build/classes \
      $(find src build/gen -name '*.java')
if command -v d8 >/dev/null; then
  d8 --min-api 26 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
else
  dalvik-exchange --dex --min-sdk-version=26 --output=build/dex/classes.dex build/classes
fi
(cd build/dex && aapt add ../app.unsigned.apk classes.dex >/dev/null)
zipalign -f 4 build/app.unsigned.apk build/app.aligned.apk
KS=${KEYSTORE:-debug.keystore}
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android -alias pocket \
          -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Pocket Link Test" >/dev/null 2>&1
fi
apksigner sign --ks "$KS" --ks-pass pass:android --key-pass pass:android --out PocketLinkTest.apk build/app.aligned.apk
apksigner verify PocketLinkTest.apk && echo "built $(pwd)/PocketLinkTest.apk"
