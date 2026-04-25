[app]
title = ParkingTV
package.name = parkingtv
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,ttf,otf
version = 0.1
requirements = python3,kivy==2.3.1,requests,chardet,filetype,pyjnius
orientation = landscape
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,REQUEST_EXTERNAL_STORAGE
android.api = 27
android.minapi = 21
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.install_location = auto
android.icon =
android.extra_manifest_elements = <uses-feature android:name="android.software.leanback" android:required="false" /><uses-feature android:name="android.hardware.touchscreen" android:required="false" /><uses-feature android:name="android.hardware.faketouch" android:required="false" />
android.extra_manifest_launch_intent_category_elements = <category android:name="android.intent.category.LEANBACK_LAUNCHER" />

[buildozer]
log_level = 2
warn_on_root = 0
build_timeout = 3600