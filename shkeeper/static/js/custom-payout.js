const crypto = document.getElementById('cryptoname').getAttribute("cryptoname");
const BTC = "BTC";
const LTC = "LTC";
const DOGE = "DOGE";
function dropdown()
{
  function addEventsToDropdown()
  {
    let dropdownBtn = document.querySelectorAll('.dropdown__button');
    let dropdownItems = document.querySelectorAll('.dropdown__text');
    let dropdownCurrent = document.querySelectorAll('.dropdown__current');
    dropdownCurrent.forEach( item=>{
        item.addEventListener('click',function(){
            document.querySelectorAll('.dropdown__body')[0].classList.add("dropdown-show");
        });
    });

    dropdownBtn.forEach( item=>{
        item.addEventListener('click',toggleDropdown);
    });

    dropdownItems.forEach( item=>{ item.addEventListener('click',chooseItem);});

  }
  function autocomplete()
  {
    let addressField = document.getElementById("paddress");
    function filterAddItems()
    {
        let dropdownItems = document.querySelectorAll('.dropdown__item');
        dropdownItems.forEach(item => {
            let itemValue = item.querySelector('.dropdown__text').innerText;
            let re = new RegExp(addressField.value);
            console.log(re.test(itemValue));
            if(!re.test(itemValue) && addressField.value != "")
            {
                item.classList.add("dropdown__item-hide");
            }
            else{
                item.classList.remove("dropdown__item-hide");
            }
        });
    }
    filterAddItems()
    addressField.addEventListener('keyup',function(){filterAddItems()});
  }

  function toggleDropdown()
  {
    let dropdownBody=document.querySelectorAll('.dropdown__body');
    dropdownBody.forEach(item => {item.classList.toggle('dropdown-show');});
  }
  function chooseItem()
  {
    let value = this.innerText;
    let paddress = document.getElementById("paddress");
    paddress.value = value;
    toggleDropdown();
  }
  addEventsToDropdown();
  autocomplete();
  window.onclick = function(event){
    if(event.target.localName != ("svg" || "use")){
        if(!event.target.className.match('dropdown'))
        {
        let dropdowns = document.querySelectorAll('.dropdown__body');
        dropdowns.forEach( item=>{
            item.classList.remove("dropdown-show");
        });
        }
    }
  }
}

function refreshAddList()
{
    function getAddListSS()
    {
        let requestBody = JSON.stringify(
            {
              action: "list"
            }
        );
        let listHttp = new XMLHttpRequest();
        listHttp.open('POST',"/api/v1/" + crypto + "/payout_destinations",true);
        listHttp.send(requestBody);
        listHttp.onload = function()
        {
            let data = checkAnswer(this.responseText);
            if(data == false)
            {
                console.log("Error, or empty list!");
            }
            else{
                clearDropdownBody();
                data['payout_destinations'].forEach(item=>{
                    addHTMLElement(item['addr']);
                });
            }


        };


    }
    function chooseItem()
    {
        let value = this.innerText;
        let paddress = document.getElementById("paddress");
        paddress.value = value;
        toggleDropdown();
    }
    function checkAnswer(responseText)
    {
        let data = JSON.parse(responseText);
        if(data['status'] != "success")
        {
            return false;
        }
        else
        {
            return data;
        }
    }
    function createEmpEnt(addr,comment)
    {
      let itemSample = document.querySelector('.dropdown__item-sample');
      let newEnt = itemSample.cloneNode(true);
      newEnt.classList.remove("dropdown__item-sample");
      newEnt.classList.add("dropdown__item");
      let textField = newEnt.querySelector('.dropdown__text');
      textField.innerHTML = addr;
      return newEnt;
    }
    function addHTMLElement(addr,comment)
    {
      let itemSample = createEmpEnt(addr,comment);
      let managerNode = document.querySelector('.dropdown__body');
      managerNode.appendChild(itemSample);
      itemSample.addEventListener('click',chooseItem);
    }
    function clearDropdownBody()
    {
        let itemList = document.getElementsByClassName('dropdown__item');
        while(itemList.length > 0){
            itemList[0].parentNode.removeChild(itemList[0]);
        }
    }
    getAddListSS();
}

function addAddress()
{
  let data = composeAddData();
  let http = new XMLHttpRequest();
  http.onload = function(){
    console.log("Ok!");
    location.reload();
  }
  http.open("POST","/api/v1/" + crypto + "/payout_destinations",true);
  if(data != false)
  {
    http.send(data);
  }
  else
  {
    alert("Please, Fields cannot be empty or check if the values are entered correctly.")
  }
  function composeAddData()
  {
    let check = true;
    let payoutAdd = validateAddressValue(document.querySelector('.dropdown__current'));
    if(check == false)
    {
      return false;
    }

    return JSON.stringify({
      action: "add",
      daddress: payoutAdd,
      comment: "",

    });
    function validateAddressValue(element)
    {
      element.value = element.value.trim();
      if(element.value != "" && element.value != "None")
      {
        if(crypto == BTC)
        {
          let BTCRegExp = new RegExp('^(?:[13]{1}[a-km-zA-HJ-NP-Z1-9]{26,33}|bc1[a-z0-9]{39,59}|tb1[a-z0-9]{39,59})$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Bitcoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == LTC)
        {
          let LTCRegExp = new RegExp('^([LM3][a-km-zA-HJ-NP-Z1-9]{26,33}|ltc1[a-z0-9]{39,59})$');
          if(LTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Litecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == DOGE)
        {
          let DOGERegExp = new RegExp('^D{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}$');
          if(DOGERegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Dogecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }

      }
      else{
        document.querySelector(".dropdown__header").classList.add("red-highlight");
        check = false;
      }
      return element.value;
    }
  }

}
function sendPayment()
{
  let data = composeData();
  const httpPay = new XMLHttpRequest();
  httpPay.open("post","/api/v1/" + crypto + "/payout");
  if(data != false)
  {
    httpPay.send(data);
  }
  httpPay.onload = function()
  {
    if(this.status == 200)
    {
      if(checkAnswer(this.responseText))
      {
        addAddress();
      }
    }
    else
    {
      alert("Error: " + this.status);
    }
  }
  function checkAnswer(responseText)
  {
    let data = JSON.parse(responseText);
    if(data['result'] == null)
    {
      alert("Error: " + data["error"].message);
      return false;
    }
    else
    {
      alert(`Payment sent. TXID: ` + data["result"]);
      return data;
    }
  }
  function composeData()
  {
    let check = true;
    let destinationAdd = validateAddressValue(document.querySelector('.dropdown__current'));
    let amount = validateFloatValue(document.querySelector('input[name="amount"]'));
    let fee = validateFloatValue(document.querySelector('[name="fee"]'));
    if(check == false)
    {
      return false;
    }

    return JSON.stringify({
      destination: destinationAdd,
      fee: fee,
      amount: amount
    });
    function validateFloatValue(element)
    {
      element.value = element.value.trim();
      if(element.value.match(/^\d+\.*\d*$/))
      {
        element.classList.remove("red-highlight");
      }
      else{
        element.classList.add("red-highlight");
        check = false;
      }
      return element.value;
    }
    function validateAddressValue(element)
    {
      element.value = element.value.trim();
      if(element.value != "" && element.value != "None")
      {
        if(crypto == BTC)
        {
          let BTCRegExp = new RegExp('^(?:[13]{1}[a-km-zA-HJ-NP-Z1-9]{26,33}|bc1[a-z0-9]{39,59}|tb1[a-z0-9]{39,59})$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Bitcoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == LTC)
        {
          let BTCRegExp = new RegExp('^([LM3][a-km-zA-HJ-NP-Z1-9]{26,33}|ltc1[a-z0-9]{39,59})$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Litecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == DOGE)
        {
          let BTCRegExp = new RegExp('^D{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Dogecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }

      }
      else{
        document.querySelector(".dropdown__header").classList.add("red-highlight");
        check = false;
      }
      return element.value;
    }
  }
}
let deleteAdd = function(){

  let deleteButtons = document.querySelectorAll('.delete-button');

  deleteButtons.forEach(item => {
    item.addEventListener('click', deleteAddress);
  });

  function deleteAddress()
  {
    let destinationNode = this.parentElement;
    let destinationAdd = destinationNode.firstElementChild.innerText;
    let jsonObj = JSON.stringify({
      action: "delete",
      daddress: destinationAdd
    });

    destinationNode.remove();

    const httpAPI = new XMLHttpRequest();

    httpAPI.onload = function(){
      destinationNode.remove();
    }
    httpAPI.open("POST","/api/v1/" + crypto + "/payout_destinations",true);
    httpAPI.send(jsonObj);
  }
}

document.querySelector('.send-payment').addEventListener('click',sendPayment);
dropdown();
deleteAdd();