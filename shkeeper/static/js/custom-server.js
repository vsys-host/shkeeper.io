function activeTab()
{
    document.getElementById("wallet-link").classList.add("nav-link--active");
}
function actionSKey(input)
{
    if(input.disabled == true){
        input.disabled = false;
    }else{
        input.disabled = true;
    }
    let editButton = document.getElementById("server-edit");
    if(editButton.innerHTML == "Save")
    {
        editButton.innerHTML = "Edit";
    }else{
        editButton.innerHTML = "Save";
    }
}
function getServerInput()
{
    let input = document.getElementById("inputSKey");
    input.disabled = true;
    input.maxLength = 30;
    return input;
}
/* function testServerConn(data)
{
    let editButton = document.getElementById("server-edit");
    if(editButton.innerHTML == "Edit" && data != "")
    {
        const http = new XMLHttpRequest();
        http.onload = function(){
            let status = document.getElementById("server-status");
            if(this.responseText == "ok")
            {
                status.innerHTML = "Server online";
                status.classList.add("server-active");
                status.classList.remove("server-inactive");
            }
            else{
                status.innerHTML = "Server offline";
                status.classList.remove("server-active");
                status.classList.add("server-inactive");
            }
        }
        http.open("POST","/api",true);
        let jsonObj = {
            crypto: "btc",
            source: "internal",
            action: "pingserver",
            key: data
        };
        http.setRequestHeader("Content-Type", "application/json");
        http.send(JSON.stringify(jsonObj));
    }else{
        alert("Input and save Server Key");
    }
} */

//activeTab();
/* let input = getServerInput();
document.getElementById("server-edit").addEventListener("click", function(){actionSKey(input);});

document.getElementById("server-test").addEventListener("click",function(){testServerConn(input.value);});
 */
