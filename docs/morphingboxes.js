// CSS hover doesn't work anymore since iPad came out, and CSS focus
// doesn't appear to work reliably either, so use JavaScript instead

function hasClass(el, cls) {
  var elcls = el.className.split( " " );
  for ( var i = 0; i < elcls.length; i++ ) {
    if ( elcls[i] == cls ) return true;
  }
  return false;
}

function morphclick(el) {

  var kids = el.childNodes;
  var firstkid = null, madeinvis = false, madevis = false;
  for (var i = 0; i < kids.length; i++) {
    var kid = kids[i];
    if (kid.nodeType != 1) continue; // not a div
    firstkid = firstkid || kid;
    var hid = kid.style.display == 'none';
    if (!hid) {
      kid.style.display = 'none';
      madeinvis = true;
    } else if (madeinvis) {
      if (!madevis) kid.style.display = 'block';
      madevis = true;
    }
  }
  if (!madevis && firstkid) {
    firstkid.style.display = 'block';
  }
  if (!firstkid) {
    alert("oops! morphing block has no kids");
  }
}

function setupmorphingboxes() {
  document.documentElement.className += " js";
  var divs = document.getElementsByTagName('div');
  for (var i = 0; i < divs.length; i++) {
    var el = divs[i];
    if (!hasClass(el, 'morphing')) continue;
    morphclick(el);
    el.addEventListener('click', function(e){
      morphclick(this);
      return;
      e = e || window.event;
      morphclick(e.target || e.srcElement);
    }, false);
  }
}

if (window.addEventListener
    && document.getElementsByTagName) {
  window.addEventListener("load", setupmorphingboxes, false);
}
