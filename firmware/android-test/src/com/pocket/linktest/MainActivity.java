package com.pocket.linktest;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Settings + live log for the Pocket Link bench test. */
public class MainActivity extends Activity implements BridgeService.Ui {
    private EditText url, token, allowed;
    private CheckBox autoAnswer, bridgeAll;
    private TextView status, log;
    private ScrollView scroll;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        SharedPreferences p = getSharedPreferences("cfg", MODE_PRIVATE);
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);

        url = field(root, "Voice engine WebSocket URL", p.getString("url", "ws://127.0.0.1:8793/audio"), false);
        token = field(root, "Bearer token (from bridge-token file)", p.getString("token", ""), true);
        allowed = field(root, "Allowed caller number (with country code)", p.getString("allowed", ""), false);
        allowed.setInputType(InputType.TYPE_CLASS_PHONE);
        autoAnswer = new CheckBox(this);
        autoAnswer.setText("Auto-answer the allowed caller");
        autoAnswer.setChecked(p.getBoolean("autoAnswer", true));
        root.addView(autoAnswer);
        bridgeAll = new CheckBox(this);
        bridgeAll.setText("Also bridge calls I answer myself (e.g. WhatsApp)");
        bridgeAll.setChecked(p.getBoolean("bridgeAll", false));
        root.addView(bridgeAll);

        LinearLayout row = new LinearLayout(this);
        Button start = new Button(this);
        start.setText("Start");
        Button stop = new Button(this);
        stop.setText("Stop");
        row.addView(start);
        row.addView(stop);
        root.addView(row);

        status = new TextView(this);
        status.setText("Adapter status: —");
        status.setPadding(0, pad / 2, 0, pad / 2);
        root.addView(status);

        scroll = new ScrollView(this);
        log = new TextView(this);
        log.setTypeface(Typeface.MONOSPACE);
        log.setTextSize(12);
        scroll.addView(log);
        root.addView(scroll, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);

        start.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                save();
                askPermissions();
                Intent i = new Intent(MainActivity.this, BridgeService.class);
                try { // API 26+
                    MainActivity.class.getMethod("startForegroundService", Intent.class).invoke(MainActivity.this, i);
                } catch (Exception e) {
                    startService(i);
                }
            }
        });
        stop.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                stopService(new Intent(MainActivity.this, BridgeService.class));
            }
        });
        askPermissions();
    }

    private EditText field(LinearLayout root, String hint, String value, boolean secret) {
        TextView l = new TextView(this);
        l.setText(hint);
        root.addView(l);
        EditText e = new EditText(this);
        e.setSingleLine(true);
        e.setText(value);
        if (secret) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(e);
        return e;
    }

    private void save() {
        getSharedPreferences("cfg", MODE_PRIVATE).edit()
                .putString("url", url.getText().toString().trim())
                .putString("token", token.getText().toString().trim())
                .putString("allowed", allowed.getText().toString().trim())
                .putBoolean("autoAnswer", autoAnswer.isChecked())
                .putBoolean("bridgeAll", bridgeAll.isChecked())
                .apply();
    }

    private void askPermissions() {
        requestPermissions(new String[]{
                "android.permission.READ_PHONE_STATE",
                "android.permission.READ_CALL_LOG",
                "android.permission.ANSWER_PHONE_CALLS",
                "android.permission.POST_NOTIFICATIONS"}, 1);
    }

    @Override
    protected void onResume() {
        super.onResume();
        BridgeService.ui = this;
        if (getIntent() != null && "android.hardware.usb.action.USB_DEVICE_ATTACHED".equals(getIntent().getAction())
                && BridgeService.running) {
            startService(new Intent(this, BridgeService.class)); // re-check the adapter
        }
    }

    @Override
    protected void onPause() {
        BridgeService.ui = null;
        super.onPause();
    }

    @Override
    public void log(final String line) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                log.append(line + "\n");
                scroll.post(new Runnable() {
                    @Override
                    public void run() {
                        scroll.fullScroll(View.FOCUS_DOWN);
                    }
                });
            }
        });
    }

    @Override
    public void status(final String line) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                status.setText(line);
            }
        });
    }
}
