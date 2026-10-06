/// Interface text that has NO equivalent in the web app (web/src/i18n/en.ts, hi.ts).
///
/// Everything else comes verbatim from the web app via lib/generated/web_data.g.dart.
/// Keep this list short: each entry here is new wording that needs the owner's review
/// (the Hindi entries are developer drafts, like the web app's Hindi text).
library;

const Map<String, Object> mobileEn = <String, Object>{
  // Server status banner (the web app's equivalents all mention demo mode, which the app lacks).
  'mobile.unreachableTitle': "Can't reach the analysis server",
  'mobile.unreachableBody': 'It may be asleep or starting up. Checks will fail until it is back.',
  'mobile.notConfiguredTitle': 'No analysis server is set up for this app yet',
  'mobile.insecureTitle': 'This build has an insecure server address, so it is switched off',

  // Replaces the web "...for this site" / "Your browser sent..." wording.
  'mobile.errors.not_configured': 'No analysis server is configured for this app.',
  'mobile.errors.length_required': 'The app sent an incomplete request. Please try again.',

  // Home
  'mobile.samplesIntro': 'Tap a sample to check it.',
  'mobile.pickHint': 'Choose a screenshot from your phone. PNG, JPEG or WebP, up to 5 MB.',
  'mobile.changeImage': 'Choose a different screenshot',
  'mobile.displayOptions': 'Display options',

  // Results
  'mobile.sharedText': 'Shared from another app: text',
  'mobile.sharedImage': 'Shared from another app: screenshot',
  'mobile.checkAnother': 'Check another message',
  'mobile.tryAgain': 'Try again',
  'mobile.showText': 'Show the text',

  // Results (Phase 11b redesign; pending the owner's review with the other drafts)
  'mobile.firstStep': 'Do this first',
  'mobile.detailsHeading': 'More details',
  'mobile.stillWorking': 'Still working. Screenshots can take up to 30 seconds.',
  'mobile.noWarningSignsTitle': 'No warning signs',
  'mobile.retryIn': 'Try again in {s} s',

  // Share intent
  'mobile.shareUnsupported':
      "That can't be checked. Share the text of a message, or a single screenshot (PNG, JPEG or WebP).",
  'mobile.shareReadFailed': "The shared item couldn't be read. Try sharing it again, or paste the text.",

  // About
  'mobile.shareHeading': 'Checking messages from other apps',
  'mobile.shareTips': <String>[
    'In most apps, choose Share and then Scam Message Checker. The check starts straight away.',
    'Gmail has no option to share a whole email. Select the text and choose Share, or copy it and paste it here.',
    "WhatsApp doesn't always offer Share for a text message. Copy the message and paste it here, or share a screenshot instead.",
  ],
  'mobile.privacyApp': <String>[
    'This app contains no keys or passwords and talks only to the project\'s own API.',
    'Nothing is saved on your phone: no history, no settings, and shared messages and screenshots are kept only in memory.',
  ],
  'mobile.licences': 'Open-source licences',
};

const Map<String, Object> mobileHi = <String, Object>{
  'mobile.unreachableTitle': 'जाँच सर्वर तक नहीं पहुँच पा रहे',
  'mobile.unreachableBody': 'हो सकता है वह सो रहा हो या शुरू हो रहा हो। उसके वापस आने तक जाँच नहीं हो पाएगी।',
  'mobile.notConfiguredTitle': 'इस ऐप के लिए अभी कोई जाँच सर्वर सेट नहीं है',
  'mobile.insecureTitle': 'इस बिल्ड में सर्वर का पता सुरक्षित नहीं है, इसलिए जाँच बंद है',
  'mobile.errors.not_configured': 'इस ऐप के लिए कोई जाँच सर्वर सेट नहीं है।',
  'mobile.errors.length_required': 'ऐप ने अधूरा अनुरोध भेजा। कृपया फिर से कोशिश करें।',
  'mobile.samplesIntro': 'किसी सैंपल को जाँचने के लिए उस पर टैप करें।',
  'mobile.pickHint': 'अपने फ़ोन से एक स्क्रीनशॉट चुनें। PNG, JPEG या WebP, 5 MB तक।',
  'mobile.changeImage': 'दूसरा स्क्रीनशॉट चुनें',
  'mobile.displayOptions': 'दिखावट के विकल्प',
  'mobile.sharedText': 'दूसरे ऐप से शेयर किया गया: टेक्स्ट',
  'mobile.sharedImage': 'दूसरे ऐप से शेयर किया गया: स्क्रीनशॉट',
  'mobile.checkAnother': 'दूसरा मैसेज जाँचें',
  'mobile.tryAgain': 'फिर से कोशिश करें',
  'mobile.showText': 'टेक्स्ट दिखाएँ',
  'mobile.firstStep': 'सबसे पहले यह करें',
  'mobile.detailsHeading': 'और जानकारी',
  'mobile.stillWorking': 'अभी जाँच चल रही है। स्क्रीनशॉट में 30 सेकंड तक लग सकते हैं।',
  'mobile.noWarningSignsTitle': 'कोई चेतावनी संकेत नहीं',
  'mobile.retryIn': '{s} सेकंड में फिर कोशिश करें',
  'mobile.shareUnsupported':
      'इसे जाँचा नहीं जा सकता। किसी मैसेज का टेक्स्ट, या एक स्क्रीनशॉट (PNG, JPEG या WebP) शेयर करें।',
  'mobile.shareReadFailed': 'शेयर की गई चीज़ पढ़ी नहीं जा सकी। फिर से शेयर करें, या टेक्स्ट पेस्ट करें।',
  'mobile.shareHeading': 'दूसरे ऐप से मैसेज जाँचना',
  'mobile.shareTips': <String>[
    'ज़्यादातर ऐप में Share चुनें और फिर Scam Message Checker। जाँच तुरंत शुरू हो जाती है।',
    'Gmail में पूरा ईमेल शेयर करने का विकल्प नहीं है। टेक्स्ट चुनकर Share करें, या उसे कॉपी करके यहाँ पेस्ट करें।',
    'WhatsApp में टेक्स्ट मैसेज के लिए Share हमेशा नहीं मिलता। मैसेज कॉपी करके यहाँ पेस्ट करें, या उसका स्क्रीनशॉट शेयर करें।',
  ],
  'mobile.privacyApp': <String>[
    'इस ऐप में कोई की या पासवर्ड नहीं है, और यह सिर्फ़ प्रोजेक्ट के अपने API से बात करता है।',
    'आपके फ़ोन पर कुछ भी सेव नहीं होता: न हिस्ट्री, न सेटिंग। शेयर किए गए मैसेज और स्क्रीनशॉट सिर्फ़ मेमोरी में रहते हैं।',
  ],
  'mobile.licences': 'ओपन-सोर्स लाइसेंस',
};
