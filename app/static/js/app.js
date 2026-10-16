function showLogin(){document.getElementById("loginModal").hidden=false}
function hideLogin(){document.getElementById("loginModal").hidden=true}

function addActivity(){const t=document.getElementById('activityTpl');document.getElementById('activities').appendChild(t.content.cloneNode(true));}
